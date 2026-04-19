import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("./hooks/useDiagnosticsModel", () => ({
  useDiagnosticsModel: () => ({
    isError: false,
    data: {
      source_mode: "resolved",
      summary: {
        app_name: "Botik Foundation",
        version: "1",
        app_service_base_url: "http://127.0.0.1:8765",
        desktop_mode: false,
        runtime_control_mode: "fixture",
        routes_count: 10,
        fixture_overrides_count: 7,
        missing_paths_count: 1,
        warnings_count: 2,
      },
      config: [
        {
          key: "session_token",
          label: "Session Token",
          value: "bot***ken",
          masked: true,
        },
      ],
      paths: [
        {
          key: "runtime_status_fixture",
          label: "Runtime Status Fixture",
          path: "C:/tmp/runtime-status.fixture.json",
          source: "fixture",
          exists: true,
          kind: "file",
        },
      ],
      warnings: [
        "Legacy compatibility DB path is missing.",
        "Runtime control is currently configured in fixture mode.",
      ],
    },
  }),
}));

import { DiagnosticsPage } from "./DiagnosticsPage";

describe("DiagnosticsPage", () => {
  it("renders the bounded diagnostics compatibility snapshot", () => {
    const queryClient = new QueryClient();

    render(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          React.createElement(DiagnosticsPage),
        ),
      ),
    );

    expect(screen.getByRole("heading", { name: "Диагностика совместимости" })).toBeTruthy();
    expect(screen.getByTestId("diagnostics.source-mode").textContent).toContain("resolved");
    expect(screen.getByTestId("diagnostics.summary.routes").textContent).toContain("10");
    expect(screen.getByTestId("diagnostics.summary.fixtures").textContent).toContain("7");
    expect(screen.getByTestId("diagnostics.config.0").textContent).toContain("bot***ken");
    expect(screen.getByTestId("diagnostics.path.runtime_status_fixture").textContent).toContain("fixture");
    expect(screen.getByTestId("diagnostics.warning.1").textContent).toContain("Runtime control is currently configured");
  });
});
