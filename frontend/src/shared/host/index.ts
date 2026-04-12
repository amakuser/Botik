declare global {
  interface Window {
    __BOTIK_HOST__?: Partial<HostRuntimeConfig>;
  }
}

export interface HostRuntimeConfig {
  appServiceUrl: string;
  sessionToken: string;
  desktop: boolean;
}

export async function getHostRuntimeConfig(): Promise<HostRuntimeConfig> {
  const injected = typeof window !== "undefined" ? window.__BOTIK_HOST__ : undefined;
  const env = import.meta.env;

  return {
    appServiceUrl: injected?.appServiceUrl ?? env.VITE_BOTIK_APP_SERVICE_URL ?? "http://127.0.0.1:8765",
    sessionToken: injected?.sessionToken ?? env.VITE_BOTIK_SESSION_TOKEN ?? "botik-dev-token",
    desktop: injected?.desktop ?? env.VITE_BOTIK_DESKTOP === "true",
  };
}
