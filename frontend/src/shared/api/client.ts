import {
  BootstrapPayload,
  HealthResponse,
  JobDetails,
  JobSummary,
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
