mod app_service;
mod host_api;

use std::io;
use std::sync::Mutex;

use app_service::{shutdown_managed_app_service, start_managed_app_service, ManagedAppServiceState};
use host_api::get_runtime_config;
use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let managed = start_managed_app_service()
                .map_err(|message| io::Error::new(io::ErrorKind::Other, message))?;
            let runtime_config = managed.runtime_config.clone();
            app.manage(runtime_config);
            app.manage(Mutex::new(Some(managed)));
            Ok(())
        })
        .on_page_load(|window, _payload| {
            let runtime_config = window.state::<host_api::RuntimeConfig>();
            if let Ok(json) = serde_json::to_string(&*runtime_config) {
                let script = format!(
                    "window.__BOTIK_HOST__ = Object.assign(window.__BOTIK_HOST__ ?? {{}}, {});",
                    json
                );
                let _ = window.eval(&script);
            }
        })
        .invoke_handler(tauri::generate_handler![get_runtime_config])
        .build(tauri::generate_context!())
        .expect("failed to build Botik desktop shell")
        .run(|app_handle, event| {
            if matches!(event, tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit) {
                let state = app_handle.state::<ManagedAppServiceState>();
                shutdown_managed_app_service(&state);
            }
        });
}
