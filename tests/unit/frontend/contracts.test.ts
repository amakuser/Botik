import { describe, expect, it } from "vitest";
import { contractSchemaNames } from "../../../frontend/src/shared/contracts";

describe("generated contracts", () => {
  it("exposes the expected schema names", () => {
    expect(contractSchemaNames).toContain("HealthResponse");
    expect(contractSchemaNames).toContain("BootstrapPayload");
    expect(contractSchemaNames).toContain("JobDetails");
    expect(contractSchemaNames).toContain("DataBackfillJobPayload");
    expect(contractSchemaNames).toContain("DataIntegrityJobPayload");
    expect(contractSchemaNames).toContain("TrainingControlJobPayload");
    expect(contractSchemaNames).toContain("LogChannelSnapshot");
    expect(contractSchemaNames).toContain("RuntimeStatusSnapshot");
    expect(contractSchemaNames).toContain("FuturesReadSnapshot");
    expect(contractSchemaNames).toContain("SpotReadSnapshot");
    expect(contractSchemaNames).toContain("TelegramOpsSnapshot");
    expect(contractSchemaNames).toContain("TelegramConnectivityCheckResult");
    expect(contractSchemaNames).toContain("AnalyticsReadSnapshot");
    expect(contractSchemaNames).toContain("AnalyticsSummary");
    expect(contractSchemaNames).toContain("ModelsReadSnapshot");
    expect(contractSchemaNames).toContain("ModelsSummary");
  });
});
