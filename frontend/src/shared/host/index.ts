declare global {
  interface Window {
    __BOTIK_HOST__?: Partial<HostRuntimeConfig>;
    __TAURI_INTERNALS__?: unknown;
  }
}

export interface HostRuntimeConfig {
  appServiceUrl: string;
  sessionToken: string;
  desktop: boolean;
}

function readHostRuntimeConfig(): HostRuntimeConfig {
  const injected = typeof window !== "undefined" ? window.__BOTIK_HOST__ : undefined;
  const env = import.meta.env;

  return {
    appServiceUrl: injected?.appServiceUrl ?? env.VITE_BOTIK_APP_SERVICE_URL ?? "http://127.0.0.1:8765",
    sessionToken: injected?.sessionToken ?? env.VITE_BOTIK_SESSION_TOKEN ?? "botik-dev-token",
    desktop: injected?.desktop ?? env.VITE_BOTIK_DESKTOP === "true",
  };
}

export function getHostRuntimeConfigSync(): HostRuntimeConfig {
  return readHostRuntimeConfig();
}

export async function getHostRuntimeConfig(): Promise<HostRuntimeConfig> {
  return readHostRuntimeConfig();
}

export function isDesktopRuntime(): boolean {
  // __TAURI_INTERNALS__ is injected by Tauri v2 before any JS runs
  if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) return true;
  return readHostRuntimeConfig().desktop;
}
