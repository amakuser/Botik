use serde::Serialize;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeConfig {
    pub app_service_url: String,
    pub session_token: String,
    pub desktop: bool,
}

#[tauri::command]
pub fn get_runtime_config(state: tauri::State<'_, RuntimeConfig>) -> RuntimeConfig {
    state.inner().clone()
}
