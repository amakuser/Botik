import {
  BootstrapPayload,
  HealthResponse,
  JobDetails,
  JobEvent,
  LogChannel,
  LogChannelSnapshot,
  LogStreamEvent,
  LogEvent,
  RuntimeStatusSnapshot,
  RuntimeId,
  JobSummary,
  SpotReadSnapshot,
  StartJobRequest,
  StopJobRequest,
} from "../contracts";
import { loadRuntimeConfig } from "../config";

async function authenticatedFetch(path: string, init?: RequestInit): Promise<Response> {
  const runtime = await loadRuntimeConfig();
  const url = new URL(path, runtime.appServiceUrl);

  const headers = new Headers(init?.headers ?? {});
  headers.set("x-botik-session-token", runtime.sessionToken);

  return fetch(url, {
    ...init,
    headers,
  });
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await authenticatedFetch("/health");
  return parseJsonOrThrow<HealthResponse>(response);
}

export async function getBootstrap(): Promise<BootstrapPayload> {
  const response = await authenticatedFetch("/bootstrap");
  return parseJsonOrThrow<BootstrapPayload>(response);
}

export async function listJobs(): Promise<JobSummary[]> {
  const response = await authenticatedFetch("/jobs");
  return parseJsonOrThrow<JobSummary[]>(response);
}

export async function getJob(jobId: string): Promise<JobDetails> {
  const response = await authenticatedFetch(`/jobs/${jobId}`);
  return parseJsonOrThrow<JobDetails>(response);
}

export async function startJob(request: StartJobRequest): Promise<JobDetails> {
  const response = await authenticatedFetch("/jobs", {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(request),
  });
  return parseJsonOrThrow<JobDetails>(response);
}

export async function stopJob(jobId: string, request: StopJobRequest): Promise<JobDetails> {
  const response = await authenticatedFetch(`/jobs/${jobId}/stop`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(request),
  });
  return parseJsonOrThrow<JobDetails>(response);
}

export async function createEventSource(): Promise<EventSource> {
  const runtime = await loadRuntimeConfig();
  const url = new URL("/events", runtime.appServiceUrl);
  url.searchParams.set("session_token", runtime.sessionToken);
  return new EventSource(url);
}

export async function listLogChannels(): Promise<LogChannel[]> {
  const response = await authenticatedFetch("/logs/channels");
  return parseJsonOrThrow<LogChannel[]>(response);
}

export async function getLogSnapshot(channelId: string): Promise<LogChannelSnapshot> {
  const response = await authenticatedFetch(`/logs/${channelId}`);
  return parseJsonOrThrow<LogChannelSnapshot>(response);
}

export async function createLogEventSource(channelId: string): Promise<EventSource> {
  const runtime = await loadRuntimeConfig();
  const url = new URL(`/logs/${channelId}/stream`, runtime.appServiceUrl);
  url.searchParams.set("session_token", runtime.sessionToken);
  return new EventSource(url);
}

export async function getRuntimeStatus(): Promise<RuntimeStatusSnapshot> {
  const response = await authenticatedFetch("/runtime-status");
  return parseJsonOrThrow<RuntimeStatusSnapshot>(response);
}

export async function startRuntime(runtimeId: RuntimeId): Promise<RuntimeStatus> {
  const response = await authenticatedFetch(`/runtime-control/${runtimeId}/start`, {
    method: "POST",
  });
  return parseJsonOrThrow<RuntimeStatus>(response);
}

export async function stopRuntime(runtimeId: RuntimeId): Promise<RuntimeStatus> {
  const response = await authenticatedFetch(`/runtime-control/${runtimeId}/stop`, {
    method: "POST",
  });
  return parseJsonOrThrow<RuntimeStatus>(response);
}

export async function getSpotReadModel(): Promise<SpotReadSnapshot> {
  const response = await authenticatedFetch("/spot");
  return parseJsonOrThrow<SpotReadSnapshot>(response);
}

export interface EventPayloadMap {
  job: JobEvent;
  log: LogEvent;
}

export interface LogStreamPayloadMap {
  "log-entry": LogStreamEvent;
}
