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
export type SampleDataImportJobPayload = components["schemas"]["SampleDataImportJobPayload"];
export type DataBackfillJobPayload = components["schemas"]["DataBackfillJobPayload"];
export type DataIntegrityJobPayload = components["schemas"]["DataIntegrityJobPayload"];
export type LogChannel = components["schemas"]["LogChannel"];
export type LogEntry = components["schemas"]["LogEntry"];
export type LogChannelSnapshot = components["schemas"]["LogChannelSnapshot"];
export type LogStreamEvent = components["schemas"]["LogStreamEvent"];
export type RuntimeStatus = components["schemas"]["RuntimeStatus"];
export type RuntimeStatusSnapshot = components["schemas"]["RuntimeStatusSnapshot"];
export type RuntimeId = RuntimeStatus["runtime_id"];

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
  "SampleDataImportJobPayload",
  "DataBackfillJobPayload",
  "DataIntegrityJobPayload",
  "LogChannel",
  "LogEntry",
  "LogChannelSnapshot",
  "LogStreamEvent",
  "RuntimeStatus",
  "RuntimeStatusSnapshot",
] as const;
