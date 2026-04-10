import type { components } from "./generated";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type AppSessionInfo = components["schemas"]["AppSessionInfo"];
export type UiCapabilities = components["schemas"]["UiCapabilities"];
export type BootstrapPayload = components["schemas"]["BootstrapPayload"];
export type JobSummary = components["schemas"]["JobSummary"];
export type JobDetails = components["schemas"]["JobDetails"];
export type JobState = components["schemas"]["JobState"];
export type StartJobRequest = components["schemas"]["StartJobRequest"];
export type StopJobRequest = components["schemas"]["StopJobRequest"];
export type JobEvent = components["schemas"]["JobEvent"];
export type LogEvent = components["schemas"]["LogEvent"];
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

export const contractSchemaNames = [
  "HealthResponse",
  "AppSessionInfo",
  "UiCapabilities",
  "BootstrapPayload",
  "JobSummary",
  "JobDetails",
  "JobState",
  "StartJobRequest",
  "StopJobRequest",
  "JobEvent",
  "LogEvent",
  "ErrorEnvelope",
] as const;
