import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getTelegramOpsModel: vi.fn(),
  runTelegramConnectivityCheck: vi.fn(),
}));

vi.mock("../../shared/api/client", () => ({
  getTelegramOpsModel: mocks.getTelegramOpsModel,
  runTelegramConnectivityCheck: mocks.runTelegramConnectivityCheck,
}));

import { TelegramPage } from "./TelegramPage";

describe("TelegramPage", () => {
  beforeEach(() => {
    mocks.getTelegramOpsModel.mockResolvedValue({
      generated_at: "2026-04-11T12:00:00Z",
      source_mode: "fixture",
      summary: {
        bot_profile: "ops",
        token_profile_name: "TELEGRAM_BOT_TOKEN",
        token_configured: true,
        internal_bot_disabled: false,
        connectivity_state: "unknown",
        connectivity_detail: "Use connectivity check to verify Telegram Bot API reachability.",
        allowed_chat_count: 2,
        allowed_chats_masked: ["12***34", "56***78"],
        commands_count: 2,
        alerts_count: 1,
        errors_count: 1,
        last_successful_send: "fixture alert delivered",
        last_error: "fixture warning observed",
        startup_status: "configured",
      },
      recent_commands: [
        {
          ts: "2026-04-11T11:58:00Z",
          command: "/status",
          source: "telegram_bot",
          status: "ok",
          chat_id_masked: "12***34",
          username: "fixture_user",
          args: "",
        },
      ],
      recent_alerts: [
        {
          ts: "2026-04-11T11:59:00Z",
          alert_type: "delivery",
          message: "fixture alert delivered",
          delivered: true,
          source: "telegram",
          status: "ok",
        },
      ],
      recent_errors: [
        {
          ts: "2026-04-11T11:57:00Z",
          error: "fixture warning observed",
          source: "telegram",
          status: "warning",
        },
      ],
      truncated: {
        recent_commands: false,
        recent_alerts: false,
        recent_errors: false,
      },
    });
    mocks.runTelegramConnectivityCheck.mockResolvedValue({
      checked_at: "2026-04-11T12:00:10Z",
      source_mode: "fixture",
      state: "healthy",
      detail: "fixture connectivity check passed",
      bot_username: "botik_fixture_bot",
      latency_ms: 42,
      error: null,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the bounded telegram ops view and runs a safe connectivity check", async () => {
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
          React.createElement(TelegramPage),
        ),
      ),
    );

    expect(await screen.findByRole("heading", { name: "Телеграм" })).toBeTruthy();
    expect((await screen.findByTestId("telegram.source-mode")).textContent).toContain("fixture");
    expect((await screen.findByTestId("telegram.summary.allowed-chats")).textContent).toContain("2");
    expect(await screen.findByTestId("telegram.command.0")).toBeTruthy();
    expect(await screen.findByTestId("telegram.alert.0")).toBeTruthy();
    expect(await screen.findByTestId("telegram.error.0")).toBeTruthy();

    fireEvent.click(await screen.findByTestId("telegram.connectivity-check"));
    await waitFor(() => expect(mocks.runTelegramConnectivityCheck).toHaveBeenCalledTimes(1));
    expect((await screen.findByTestId("telegram.check.result")).textContent).toContain("healthy");
    expect((await screen.findByTestId("telegram.check.result")).textContent).toContain("botik_fixture_bot");

    view.unmount();
    queryClient.clear();
  });
});
