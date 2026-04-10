import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  listLogChannels: vi.fn(),
  getLogSnapshot: vi.fn(),
  createLogEventSource: vi.fn(),
}));

vi.mock("../../shared/api/client", () => ({
  listLogChannels: mocks.listLogChannels,
  getLogSnapshot: mocks.getLogSnapshot,
  createLogEventSource: mocks.createLogEventSource,
}));

import { LogsPage } from "./LogsPage";

describe("LogsPage", () => {
  beforeEach(() => {
    mocks.listLogChannels.mockResolvedValue([
      { channel_id: "app", label: "App Service", source_kind: "memory", available: true },
      { channel_id: "jobs", label: "Job Events", source_kind: "events", available: true },
      { channel_id: "desktop", label: "Desktop Shell", source_kind: "file", available: false },
    ]);
    mocks.getLogSnapshot.mockResolvedValue({
      channel: "app",
      entries: [
        {
          entry_id: "entry-1",
          timestamp: "2026-04-10T00:00:00Z",
          channel: "app",
          level: "INFO",
          message: "Botik app-service started with unified logs support.",
          source: "botik_app_service",
        },
      ],
      truncated: false,
    });
    mocks.createLogEventSource.mockResolvedValue({
      addEventListener: vi.fn(),
      close: vi.fn(),
      onerror: null,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders unified logs with approved channels only", async () => {
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
          React.createElement(LogsPage),
        ),
      ),
    );

    expect(await screen.findByRole("heading", { name: "Unified Logs" })).toBeTruthy();
    expect(await screen.findByTestId("logs.channel.app")).toBeTruthy();
    expect(await screen.findByTestId("logs.channel.jobs")).toBeTruthy();
    expect(await screen.findByTestId("logs.channel.desktop")).toBeTruthy();
    expect(screen.queryByText("Telegram")).toBeNull();
    expect(await screen.findByText("Botik app-service started with unified logs support.")).toBeTruthy();
    view.unmount();
    queryClient.clear();
  });
});
