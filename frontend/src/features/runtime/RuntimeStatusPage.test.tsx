import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getRuntimeStatus: vi.fn(),
  startRuntime: vi.fn(),
  stopRuntime: vi.fn(),
}));

vi.mock("../../shared/api/client", () => ({
  getRuntimeStatus: mocks.getRuntimeStatus,
  startRuntime: mocks.startRuntime,
  stopRuntime: mocks.stopRuntime,
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
          state: "offline",
          pids: [],
          pid_count: 0,
          last_heartbeat_at: null,
          last_heartbeat_age_seconds: null,
          last_error: null,
          last_error_at: null,
          status_reason: "no matching runtime process detected",
          source_mode: "fixture",
        },
        {
          runtime_id: "futures",
          label: "Futures Runtime",
          state: "running",
          pids: [4567],
          pid_count: 1,
          last_heartbeat_at: "2026-04-11T09:59:55Z",
          last_heartbeat_age_seconds: 5,
          last_error: null,
          last_error_at: null,
          status_reason: "process present with recent heartbeat activity",
          source_mode: "fixture",
        },
      ],
    });
    mocks.startRuntime.mockResolvedValue({ runtime_id: "spot" });
    mocks.stopRuntime.mockResolvedValue({ runtime_id: "futures" });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders runtime cards with bounded start and stop controls", async () => {
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

    expect(await screen.findByRole("heading", { name: "Управление рантаймом" })).toBeTruthy();
    expect(await screen.findByTestId("runtime.card.spot")).toBeTruthy();
    expect(await screen.findByTestId("runtime.card.futures")).toBeTruthy();
    expect((await screen.findByTestId("runtime.state.spot")).textContent).toContain("OFFLINE");
    expect((await screen.findByTestId("runtime.state.futures")).textContent).toContain("RUNNING");

    const startSpot = await screen.findByTestId("runtime.start.spot");
    const stopSpot = await screen.findByTestId("runtime.stop.spot");
    const startFutures = await screen.findByTestId("runtime.start.futures");
    const stopFutures = await screen.findByTestId("runtime.stop.futures");

    expect((startSpot as HTMLButtonElement).disabled).toBe(false);
    expect((stopSpot as HTMLButtonElement).disabled).toBe(true);
    expect((startFutures as HTMLButtonElement).disabled).toBe(true);
    expect((stopFutures as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(startSpot);
    await waitFor(() => expect(mocks.startRuntime).toHaveBeenCalledWith("spot"));

    fireEvent.click(stopFutures);
    await waitFor(() => expect(mocks.stopRuntime).toHaveBeenCalledWith("futures"));

    view.unmount();
    queryClient.clear();
  });
});
