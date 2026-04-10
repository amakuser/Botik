import { getHostRuntimeConfig } from "./host";

export interface RuntimeConfig {
  appServiceUrl: string;
  sessionToken: string;
  desktop: boolean;
}

export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
  return getHostRuntimeConfig();
}
