use std::env;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use serde_json::json;

use crate::host_api::RuntimeConfig;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

const DEFAULT_APP_SERVICE_HOST: &str = "127.0.0.1";
const DEFAULT_APP_SERVICE_PORT: &str = "8765";
const DEFAULT_FRONTEND_URL: &str = "http://127.0.0.1:4173";
const DEFAULT_SESSION_TOKEN: &str = "botik-dev-token";
const DEFAULT_READY_TIMEOUT_SECS: u64 = 45;
const DEFAULT_SHUTDOWN_TIMEOUT_SECS: u64 = 10;

pub struct ManagedAppService {
    pub runtime_config: RuntimeConfig,
    child: Child,
    events_log_path: PathBuf,
}

pub type ManagedAppServiceState = Mutex<Option<ManagedAppService>>;

impl ManagedAppService {
    fn write_event(&self, kind: &str, payload: serde_json::Value) {
        append_json_line(
            &self.events_log_path,
            json!({
                "timestamp": unix_timestamp_millis(),
                "kind": kind,
                "payload": payload,
            }),
        );
    }
}

pub fn start_managed_app_service() -> Result<ManagedAppService, String> {
    let repo_root = resolve_repo_root()?;
    let host = env::var("BOTIK_APP_SERVICE_HOST").unwrap_or_else(|_| DEFAULT_APP_SERVICE_HOST.to_string());
    let port = env::var("BOTIK_APP_SERVICE_PORT").unwrap_or_else(|_| DEFAULT_APP_SERVICE_PORT.to_string());
    let session_token = env::var("BOTIK_SESSION_TOKEN").unwrap_or_else(|_| DEFAULT_SESSION_TOKEN.to_string());
    let frontend_url = env::var("BOTIK_FRONTEND_URL").unwrap_or_else(|_| DEFAULT_FRONTEND_URL.to_string());
    let python_executable = env::var("BOTIK_PYTHON_EXECUTABLE").unwrap_or_else(|_| "python".to_string());
    let artifacts_root = env::var("BOTIK_ARTIFACTS_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| repo_root.join(".artifacts").join("local").join("latest").join("desktop-shell"));

    let logs_dir = artifacts_root.join("logs");
    let structured_dir = artifacts_root.join("structured");
    fs::create_dir_all(&logs_dir).map_err(|err| format!("failed to create logs dir: {err}"))?;
    fs::create_dir_all(&structured_dir).map_err(|err| format!("failed to create structured dir: {err}"))?;

    let stdout_log_path = logs_dir.join("app-service.stdout.log");
    let stderr_log_path = logs_dir.join("app-service.stderr.log");
    let events_log_path = structured_dir.join("service-events.jsonl");

    let app_service_url = format!("http://{host}:{port}");
    let runtime_config = RuntimeConfig {
        app_service_url: app_service_url.clone(),
        session_token: session_token.clone(),
        desktop: true,
    };

    append_json_line(
        &events_log_path,
        json!({
            "timestamp": unix_timestamp_millis(),
            "kind": "spawn_requested",
            "payload": {
                "appServiceUrl": runtime_config.app_service_url,
                "frontendUrl": frontend_url,
            },
        }),
    );

    let app_service_src = repo_root.join("app-service").join("src");
    let python_path_separator = if cfg!(windows) { ";" } else { ":" };
    let python_path = format!(
        "{}{}{}",
        app_service_src.display(),
        python_path_separator,
        repo_root.display()
    );

    let stdout_file = File::create(&stdout_log_path)
        .map_err(|err| format!("failed to create app-service stdout log: {err}"))?;
    let stderr_file = File::create(&stderr_log_path)
        .map_err(|err| format!("failed to create app-service stderr log: {err}"))?;

    let mut command = Command::new(python_executable);
    command
        .arg("-m")
        .arg("uvicorn")
        .arg("botik_app_service.main:app")
        .arg("--host")
        .arg(&host)
        .arg("--port")
        .arg(&port)
        .arg("--app-dir")
        .arg(&app_service_src)
        .current_dir(&repo_root)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout_file))
        .stderr(Stdio::from(stderr_file))
        .env("PYTHONPATH", python_path)
        .env("BOTIK_APP_SERVICE_HOST", &host)
        .env("BOTIK_APP_SERVICE_PORT", &port)
        .env("BOTIK_SESSION_TOKEN", &session_token)
        .env("BOTIK_FRONTEND_URL", &frontend_url)
        .env("BOTIK_DESKTOP_MODE", "true")
        .env("BOTIK_ARTIFACTS_DIR", &artifacts_root);

    #[cfg(windows)]
    {
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let child = command
        .spawn()
        .map_err(|err| format!("failed to spawn app-service sidecar: {err}"))?;

    let mut managed = ManagedAppService {
        runtime_config,
        child,
        events_log_path,
    };
    managed.write_event(
        "spawned",
        json!({
            "pid": managed.child.id(),
        }),
    );

    wait_for_readiness(&mut managed, Duration::from_secs(DEFAULT_READY_TIMEOUT_SECS))?;
    managed.write_event("ready", json!({}));

    Ok(managed)
}

pub fn shutdown_managed_app_service(state: &ManagedAppServiceState) {
    let mut guard = match state.lock() {
        Ok(guard) => guard,
        Err(_) => return,
    };

    let Some(mut managed) = guard.take() else {
        return;
    };

    managed.write_event("shutdown_requested", json!({}));

    let shutdown_url = format!(
        "{}/admin/shutdown?session_token={}",
        managed.runtime_config.app_service_url, managed.runtime_config.session_token
    );
    let _ = ureq::post(&shutdown_url).call();

    let deadline = Instant::now() + Duration::from_secs(DEFAULT_SHUTDOWN_TIMEOUT_SECS);
    while Instant::now() < deadline {
        match managed.child.try_wait() {
            Ok(Some(status)) => {
                managed.write_event(
                    "shutdown_completed",
                    json!({
                        "exitCode": status.code(),
                    }),
                );
                return;
            }
            Ok(None) => thread::sleep(Duration::from_millis(250)),
            Err(err) => {
                managed.write_event("shutdown_wait_error", json!({ "message": err.to_string() }));
                break;
            }
        }
    }

    managed.write_event("shutdown_timeout", json!({}));
    kill_process_tree(managed.child.id());
    let _ = managed.child.wait();
    managed.write_event("kill_fallback_completed", json!({}));
}

fn wait_for_readiness(managed: &mut ManagedAppService, timeout: Duration) -> Result<(), String> {
    let deadline = Instant::now() + timeout;
    let health_url = format!("{}/health", managed.runtime_config.app_service_url);
    let agent = ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_secs(1))
        .timeout_read(Duration::from_secs(1))
        .build();
    while Instant::now() < deadline {
        if let Ok(Some(status)) = managed.child.try_wait() {
            return Err(format!("app-service exited before readiness with status: {status}"));
        }

        let response = agent
            .get(&health_url)
            .set("x-botik-session-token", &managed.runtime_config.session_token)
            .call();

        if let Ok(resp) = response {
            if resp.status() == 200 {
                return Ok(());
            }
        }

        thread::sleep(Duration::from_millis(250));
    }

    kill_process_tree(managed.child.id());
    Err(format!(
        "timed out waiting for app-service readiness at {}",
        managed.runtime_config.app_service_url
    ))
}

fn append_json_line(path: &Path, value: serde_json::Value) {
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{value}");
    }
}

fn resolve_repo_root() -> Result<PathBuf, String> {
    if let Ok(value) = env::var("BOTIK_REPO_ROOT") {
        let path = PathBuf::from(value);
        if path.join("app-service").exists() && path.join("frontend").exists() {
            return Ok(path);
        }
    }

    let mut candidates = Vec::new();
    if let Ok(current_dir) = env::current_dir() {
        candidates.push(current_dir);
    }
    if let Ok(exe_path) = env::current_exe() {
        if let Some(parent) = exe_path.parent() {
            candidates.push(parent.to_path_buf());
        }
    }

    for candidate in candidates {
        for ancestor in candidate.ancestors() {
            if ancestor.join("app-service").exists() && ancestor.join("frontend").exists() {
                return Ok(ancestor.to_path_buf());
            }
        }
    }

    Err("failed to resolve Botik repo root for desktop shell".to_string())
}

fn unix_timestamp_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or(0)
}

fn kill_process_tree(pid: u32) {
    #[cfg(windows)]
    {
        let _ = Command::new("cmd")
            .args(["/C", &format!("taskkill /PID {pid} /T /F >nul 2>nul")])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }

    #[cfg(not(windows))]
    {
        let _ = Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}
