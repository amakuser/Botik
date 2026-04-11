import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getFuturesReadModel: vi.fn(),
}));

vi.mock("../../shared/api/client", () => ({
  getFuturesReadModel: mocks.getFuturesReadModel,
}));

import { FuturesPage } from "./FuturesPage";

describe("FuturesPage", () => {
  beforeEach(() => {
    mocks.getFuturesReadModel.mockResolvedValue({
      generated_at: "2026-04-11T12:00:00Z",
      source_mode: "fixture",
      summary: {
        account_type: "UNIFIED",
        positions_count: 1,
        protected_positions_count: 1,
        attention_positions_count: 0,
        recovered_positions_count: 0,
        open_orders_count: 1,
        recent_fills_count: 1,
        unrealized_pnl_total: 42.125,
      },
      positions: [
        {
          account_type: "UNIFIED",
          symbol: "ETHUSDT",
          side: "Buy",
          position_idx: 1,
          margin_mode: "cross",
          leverage: 5,
          qty: 0.02,
          entry_price: 3000,
          mark_price: 3010.5,
          liq_price: 2500,
          unrealized_pnl: 42.125,
          take_profit: 3050,
          stop_loss: 2950,
          protection_status: "protected",
          source_of_truth: "fixture",
          recovered_from_exchange: false,
          strategy_owner: "futures_spike_reversal",
          updated_at_utc: "2026-04-11T12:00:00Z",
        },
      ],
      active_orders: [
        {
          account_type: "UNIFIED",
          symbol: "ETHUSDT",
          side: "Sell",
          order_id: "fut-order-1",
          order_link_id: "fut-link-1",
          order_type: "Limit",
          time_in_force: "GTC",
          price: 3050,
          qty: 0.02,
          status: "New",
          reduce_only: true,
          close_on_trigger: false,
          strategy_owner: "futures_spike_reversal",
          updated_at_utc: "2026-04-11T12:00:00Z",
        },
      ],
      recent_fills: [
        {
          account_type: "UNIFIED",
          symbol: "ETHUSDT",
          side: "Buy",
          exec_id: "fut-exec-1",
          order_id: "fut-order-1",
          order_link_id: "fut-link-1",
          price: 3001,
          qty: 0.02,
          exec_fee: 0.15,
          fee_currency: "USDT",
          is_maker: true,
          exec_time_ms: 1700000000123,
          created_at_utc: "2026-04-11T12:00:00Z",
        },
      ],
      truncated: {
        positions: false,
        active_orders: false,
        recent_fills: false,
      },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the bounded futures read surface without control actions", async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
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
          React.createElement(FuturesPage),
        ),
      ),
    );

    expect(await screen.findByRole("heading", { name: "Futures Read Surface" })).toBeTruthy();
    expect((await screen.findByTestId("futures.source-mode")).textContent).toContain("fixture");
    expect((await screen.findByTestId("futures.summary.positions")).textContent).toContain("1");
    expect(await screen.findByTestId("futures.position.ETHUSDT.Buy")).toBeTruthy();
    expect(await screen.findByTestId("futures.order.ETHUSDT")).toBeTruthy();
    expect(await screen.findByTestId("futures.fill.fut-exec-1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /start|stop|close|cancel|buy|sell/i })).toBeNull();
  });
});
