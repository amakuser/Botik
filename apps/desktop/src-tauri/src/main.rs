// Silent launch: avoid a flashing console host on double-click / Start-Process.
// Without this attribute the exe is built as console subsystem and Windows
// spawns a visible console window for ~100ms before WebView2 paints over it.
// With this attribute the OS does not allocate a console at all.
#![cfg_attr(all(not(debug_assertions), target_os = "windows"), windows_subsystem = "windows")]

mod app_service;
mod host_api;

use std::io;
use std::sync::Mutex;

use app_service::{shutdown_managed_app_service, start_managed_app_service, ManagedAppServiceState};
use host_api::get_runtime_config;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let managed = start_managed_app_service()
                .map_err(|message| io::Error::new(io::ErrorKind::Other, message))?;
            let runtime_config = managed.runtime_config.clone();
            app.manage(runtime_config.clone());
            app.manage(Mutex::new(Some(managed)));

            // Inject runtime config before React renders — avoids timing issues with on_page_load
            let init_script = format!(
                "window.__BOTIK_HOST__ = {{ appServiceUrl: {}, sessionToken: {}, desktop: true }};",
                serde_json::to_string(&runtime_config.app_service_url).unwrap_or_default(),
                serde_json::to_string(&runtime_config.session_token).unwrap_or_default(),
            );

            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Botik")
                .inner_size(1280.0, 800.0)
                .decorations(false)
                .resizable(true)
                .shadow(true)
                .initialization_script(&init_script)
                .build()
                .map_err(|e| io::Error::new(io::ErrorKind::Other, format!("window: {e}")))?;

            Ok(())
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
