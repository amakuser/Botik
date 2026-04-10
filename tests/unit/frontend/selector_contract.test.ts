import { describe, expect, it } from "vitest";
import { foundationSelector, selectorPriority } from "../../../test-utils/playwright/selectors";

describe("selector contract", () => {
  it("keeps the documented selector priority", () => {
    expect(selectorPriority).toEqual(["role", "label", "semantic-text", "data-testid"]);
  });

  it("creates a stable test id selector", () => {
    expect(foundationSelector("health.status")).toBe('[data-testid="health.status"]');
  });
});
