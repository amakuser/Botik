import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ModelsPage } from "./ModelsPage";

vi.mock("./hooks/useModelsReadModel", () => ({
  useModelsReadModel: () => ({
    isError: false,
    data: {
      source_mode: "fixture",
      summary: {
        total_models: 3,
        active_declared_count: 2,
        ready_scopes: 2,
        recent_training_runs_count: 2,
        latest_run_scope: "futures",
        latest_run_status: "running",
        latest_run_mode: "online",
        manifest_status: "loaded",
        db_available: true,
      },
      scopes: [
        {
          scope: "spot",
          active_model: "spot-champion-v3",
          checkpoint_name: "spot-champion-v3.pkl",
          latest_registry_model: "spot-challenger-v4",
          latest_registry_status: "candidate",
          latest_registry_created_at: "2026-04-11T10:00:00Z",
          latest_training_model_version: "spot-champion-v3",
          latest_training_status: "completed",
          latest_training_mode: "offline",
          latest_training_started_at: "2026-04-10T08:00:00Z",
          ready: true,
          status_reason: "Active model declared in active_models.yaml.",
        },
        {
          scope: "futures",
          active_model: "futures-paper-v2",
          checkpoint_name: "futures-paper-v2.pkl",
          latest_registry_model: "futures-paper-v2",
          latest_registry_status: "ready",
          latest_registry_created_at: "2026-04-11T11:00:00Z",
          latest_training_model_version: "futures-paper-v2",
          latest_training_status: "running",
          latest_training_mode: "online",
          latest_training_started_at: "2026-04-11T09:30:00Z",
          ready: true,
          status_reason: "Active model declared in active_models.yaml.",
        },
      ],
      registry_entries: [
        {
          model_id: "spot-champion-v3",
          scope: "spot",
          status: "ready",
          quality_score: 0.81,
          policy: "hybrid",
          source_mode: "executed",
          artifact_name: "spot-champion-v3.pkl",
          created_at_utc: "2026-04-10T08:00:00Z",
          is_declared_active: true,
        },
      ],
      recent_training_runs: [
        {
          run_id: "run-futures-1",
          scope: "futures",
          model_version: "futures-paper-v2",
          mode: "online",
          status: "running",
          is_trained: false,
          started_at_utc: "2026-04-11T09:30:00Z",
          finished_at_utc: "",
        },
      ],
      truncated: {
        registry_entries: false,
        recent_training_runs: false,
      },
    },
  }),
}));

vi.mock("../../shared/api/client", () => ({
  listJobs: vi.fn(async () => []),
  startJob: vi.fn(),
  stopJob: vi.fn(),
}));

describe("ModelsPage", () => {
  it("renders the bounded models registry and training status snapshot", async () => {
    const queryClient = new QueryClient();

    render(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          React.createElement(ModelsPage),
        ),
      ),
    );

    await waitFor(() => {
      expect(screen.getByTestId("models.training-control.state").textContent).toContain("idle");
    });

    expect(screen.getByRole("heading", { name: "Реестр моделей / Обучение" })).toBeTruthy();
    expect(screen.getByTestId("models.source-mode").textContent).toContain("fixture");
    expect(screen.getByTestId("models.summary.total-models").textContent).toContain("3");
    expect(screen.getByTestId("models.summary.active-declared").textContent).toContain("2");
    expect(screen.getByTestId("models.scope.spot").textContent).toContain("spot-champion-v3");
    expect(screen.getByTestId("models.scope.futures").textContent).toContain("futures-paper-v2");
    expect(screen.getByTestId("models.registry.0").textContent).toContain("spot-champion-v3");
    expect(screen.getByTestId("models.run.0").textContent).toContain("run-futures-1");
    expect(screen.getByRole("button", { name: "Запустить обучение" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Остановить обучение" })).toBeTruthy();
  });
});
