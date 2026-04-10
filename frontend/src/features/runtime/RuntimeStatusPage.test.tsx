import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getRuntimeStatus: vi.fn(),
}));

vi.mock("../../shared/api/client", () => ({
  getRuntimeStatus: mocks.getRuntimeStatus,
}));

import { RuntimeStatusPage } from "./RuntimeStatusPage";

describe("RuntimeStatusPage", () => {
  beforeEach(() => {
    mocks.getRuntimeStatus.mockResolvedValue({
      generated_at: "2026-04-11T10:00:00Z",
      runtimes: [
        {
          runtime_id: "spot",
          label: "Spot Runtime",
          state: "running",
          pids: [1234],
          pid_count: 1,
          last_heartbeat_at: "2026-04-11T09:59:55Z",
          last_heartbeat_age_seconds: 5,
          last_error: null,
          last_error_at: null,
          status_reason: "process present with recent heartbeat activity",
          source_mode: "fixture",
        },
        {
          runtime_id: "futures",
          label: "Futures Runtime",
          state: "degraded",
          pids: [4567],
          pid_count: 1,
          last_heartbeat_at: "2026-04-11T09:55:00Z",
          last_heartbeat_age_seconds: 300,
          last_error: "stale heartbeat",
          last_error_at: "2026-04-11T09:58:00Z",
          status_reason: "process present but heartbeat is stale",
          source_mode: "fixture",
        },
      ],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders spot and futures runtime cards without control actions", async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
      },
    });

    const view = render(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          React.createElement(RuntimeStatusPage),
        ),
      ),
    );

    expect(await screen.findByRole("heading", { name: "Runtime Status" })).toBeTruthy();
    expect(await screen.findByTestId("runtime.card.spot")).toBeTruthy();
    expect(await screen.findByTestId("runtime.card.futures")).toBeTruthy();
    expect((await screen.findByTestId("runtime.state.spot")).textContent).toContain("RUNNING");
    expect((await screen.findByTestId("runtime.state.futures")).textContent).toContain("DEGRADED");
    expect(screen.queryByRole("button", { name: /start/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /stop/i })).toBeNull();

    view.unmount();
    queryClient.clear();
  });
});
