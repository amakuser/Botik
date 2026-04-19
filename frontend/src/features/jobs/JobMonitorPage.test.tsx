import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  listJobs: vi.fn(),
  getJob: vi.fn(),
  startJob: vi.fn(),
  stopJob: vi.fn(),
  createEventSource: vi.fn(),
}));

vi.mock("../../shared/api/client", () => ({
  listJobs: mocks.listJobs,
  getJob: mocks.getJob,
  startJob: mocks.startJob,
  stopJob: mocks.stopJob,
  createEventSource: mocks.createEventSource,
}));

import { JobMonitorPage } from "./JobMonitorPage";

describe("JobMonitorPage", () => {
  beforeEach(() => {
    mocks.listJobs.mockResolvedValue([
      {
        job_id: "job-1",
        job_type: "data_backfill",
        state: "completed",
        progress: 1,
        updated_at: "2026-04-10T00:00:00Z",
      },
    ]);
    mocks.getJob.mockResolvedValue({
      job_id: "job-1",
      job_type: "data_backfill",
      state: "completed",
      progress: 1,
      started_at: "2026-04-10T00:00:00Z",
      updated_at: "2026-04-10T00:00:00Z",
      exit_code: 0,
      last_error: null,
      log_stream_id: "stream-1",
    });
    mocks.startJob.mockResolvedValue(undefined);
    mocks.stopJob.mockResolvedValue(undefined);
    mocks.createEventSource.mockResolvedValue({
      addEventListener: vi.fn(),
      close: vi.fn(),
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the job monitor shell with the fixed data backfill and integrity presets", async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    render(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          React.createElement(JobMonitorPage),
        ),
      ),
    );

    expect(screen.getByRole("button", { name: "Запустить импорт" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Запустить загрузку" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Запустить проверку" })).toBeTruthy();
    expect(await screen.findByText("data_backfill")).toBeTruthy();
    expect(screen.getByTestId("jobs.backfill.interval").textContent).toContain("1m");
    expect(screen.getByTestId("jobs.integrity.interval").textContent).toContain("1m");
    const state = await screen.findByTestId("jobs.selected.state");
    expect(state.textContent).toContain("completed");
  });
});
