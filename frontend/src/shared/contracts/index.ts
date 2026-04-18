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
export type SampleDataImportJobPayload = components["schemas"]["SampleDataImportJobPayload"];
export type DataBackfillJobPayload = components["schemas"]["DataBackfillJobPayload"];
export type DataIntegrityJobPayload = components["schemas"]["DataIntegrityJobPayload"];
export type TrainingControlJobPayload = components["schemas"]["TrainingControlJobPayload"];
export type LogChannel = components["schemas"]["LogChannel"];
export type LogEntry = components["schemas"]["LogEntry"];
export type LogChannelSnapshot = components["schemas"]["LogChannelSnapshot"];
export type RuntimeStatus = components["schemas"]["RuntimeStatus"];
export type RuntimeStatusSnapshot = components["schemas"]["RuntimeStatusSnapshot"];
export type RuntimeId = RuntimeStatus["runtime_id"];
export type FuturesPosition = components["schemas"]["FuturesPosition"];
export type FuturesOpenOrder = components["schemas"]["FuturesOpenOrder"];
export type FuturesFill = components["schemas"]["FuturesFill"];
export type FuturesReadSummary = components["schemas"]["FuturesReadSummary"];
export type FuturesReadSnapshot = components["schemas"]["FuturesReadSnapshot"];
export type TelegramCommandEntry = components["schemas"]["TelegramCommandEntry"];
export type TelegramAlertEntry = components["schemas"]["TelegramAlertEntry"];
export type TelegramErrorEntry = components["schemas"]["TelegramErrorEntry"];
export type TelegramOpsSummary = components["schemas"]["TelegramOpsSummary"];
export type TelegramOpsSnapshot = components["schemas"]["TelegramOpsSnapshot"];
export type TelegramConnectivityCheckResult = components["schemas"]["TelegramConnectivityCheckResult"];
export type AnalyticsSummary = components["schemas"]["AnalyticsSummary"];
export type AnalyticsEquityPoint = components["schemas"]["AnalyticsEquityPoint"];
export type AnalyticsClosedTrade = components["schemas"]["AnalyticsClosedTrade"];
export type AnalyticsReadSnapshot = components["schemas"]["AnalyticsReadSnapshot"];
export type DiagnosticsSummary = components["schemas"]["DiagnosticsSummary"];
export type DiagnosticsConfigEntry = components["schemas"]["DiagnosticsConfigEntry"];
export type DiagnosticsPathEntry = components["schemas"]["DiagnosticsPathEntry"];
export type DiagnosticsSnapshot = components["schemas"]["DiagnosticsSnapshot"];
export type ModelsSummary = components["schemas"]["ModelsSummary"];
export type ModelsScopeStatus = components["schemas"]["ModelsScopeStatus"];
export type ModelRegistryEntry = components["schemas"]["ModelRegistryEntry"];
export type TrainingRunSummary = components["schemas"]["TrainingRunSummary"];
export type ModelsReadSnapshot = components["schemas"]["ModelsReadSnapshot"];
export type SpotBalance = components["schemas"]["SpotBalance"];
export type SpotHolding = components["schemas"]["SpotHolding"];
export type SpotOrder = components["schemas"]["SpotOrder"];
export type SpotFill = components["schemas"]["SpotFill"];
export type SpotReadSummary = components["schemas"]["SpotReadSummary"];
export type SpotReadSnapshot = components["schemas"]["SpotReadSnapshot"];
export type SettingsField = components["schemas"]["SettingsField"];
export type SettingsSnapshot = components["schemas"]["SettingsSnapshot"];
export type SettingsSaveRequest = components["schemas"]["SettingsSaveRequest"];
export type SettingsSaveResult = components["schemas"]["SettingsSaveResult"];
export type BybitTestRequest = components["schemas"]["BybitTestRequest"];
export type BybitTestResult = components["schemas"]["BybitTestResult"];
export type MarketTickerEntry = components["schemas"]["MarketTickerEntry"];
export type MarketTickerSnapshot = components["schemas"]["MarketTickerSnapshot"];

// SSE/error payloads are consumed by the frontend, but they are not emitted as OpenAPI
// response models because they currently flow through StreamingResponse/manual envelopes.
export interface JobEvent {
  event_id: string;
  timestamp: string;
  kind: "job";
  job_id: string;
  job_type: string;
  state: JobState;
  progress: number;
  message?: string | null;
  phase?: string | null;
  symbol?: string | null;
  category?: string | null;
  interval?: string | null;
  completed_units?: number | null;
  total_units?: number | null;
  rows_written?: number | null;
}

export interface LogEvent {
  event_id: string;
  timestamp: string;
  kind: "log";
  job_id?: string | null;
  level: string;
  message: string;
}

export interface ErrorEnvelope {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export interface LogStreamEvent {
  type: "log-entry";
  channel: LogChannel["channel_id"];
  entry: LogEntry;
}

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
  "TrainingControlJobPayload",
  "LogChannel",
  "LogEntry",
  "LogChannelSnapshot",
  "LogStreamEvent",
  "RuntimeStatus",
  "RuntimeStatusSnapshot",
  "FuturesPosition",
  "FuturesOpenOrder",
  "FuturesFill",
  "FuturesReadSummary",
  "FuturesReadSnapshot",
  "TelegramCommandEntry",
  "TelegramAlertEntry",
  "TelegramErrorEntry",
  "TelegramOpsSummary",
  "TelegramOpsSnapshot",
  "TelegramConnectivityCheckResult",
  "AnalyticsSummary",
  "AnalyticsEquityPoint",
  "AnalyticsClosedTrade",
  "AnalyticsReadSnapshot",
  "DiagnosticsSummary",
  "DiagnosticsConfigEntry",
  "DiagnosticsPathEntry",
  "DiagnosticsSnapshot",
  "ModelsSummary",
  "ModelsScopeStatus",
  "ModelRegistryEntry",
  "TrainingRunSummary",
  "ModelsReadSnapshot",
  "SpotBalance",
  "SpotHolding",
  "SpotOrder",
  "SpotFill",
  "SpotReadSummary",
  "SpotReadSnapshot",
  "SettingsField",
  "SettingsSnapshot",
  "SettingsSaveRequest",
  "SettingsSaveResult",
  "BybitTestRequest",
  "BybitTestResult",
  "MarketTickerEntry",
  "MarketTickerSnapshot",
] as const;
