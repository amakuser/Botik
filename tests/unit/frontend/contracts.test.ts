import { describe, expect, it } from "vitest";
import { contractSchemaNames } from "../../../frontend/src/shared/contracts";

describe("generated contracts", () => {
  it("exposes the expected schema names", () => {
    expect(contractSchemaNames).toContain("HealthResponse");
    expect(contractSchemaNames).toContain("BootstrapPayload");
    expect(contractSchemaNames).toContain("JobDetails");
    expect(contractSchemaNames).toContain("DataBackfillJobPayload");
    expect(contractSchemaNames).toContain("LogChannelSnapshot");
    expect(contractSchemaNames).toContain("RuntimeStatusSnapshot");
  });
});
