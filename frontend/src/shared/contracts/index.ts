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
export type SpotBalance = components["schemas"]["SpotBalance"];
export type SpotHolding = components["schemas"]["SpotHolding"];
export type SpotOrder = components["schemas"]["SpotOrder"];
export type SpotFill = components["schemas"]["SpotFill"];
export type SpotReadSummary = components["schemas"]["SpotReadSummary"];
export type SpotReadSnapshot = components["schemas"]["SpotReadSnapshot"];

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
  "SpotBalance",
  "SpotHolding",
  "SpotOrder",
  "SpotFill",
  "SpotReadSummary",
  "SpotReadSnapshot",
] as const;
