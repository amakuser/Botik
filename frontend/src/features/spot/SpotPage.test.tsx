import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getSpotReadModel: vi.fn(),
}));

vi.mock("../../shared/api/client", () => ({
  getSpotReadModel: mocks.getSpotReadModel,
}));

import { SpotPage } from "./SpotPage";

describe("SpotPage", () => {
  beforeEach(() => {
    mocks.getSpotReadModel.mockResolvedValue({
      generated_at: "2026-04-11T12:00:00Z",
      source_mode: "fixture",
      summary: {
        account_type: "UNIFIED",
        balance_assets_count: 2,
        holdings_count: 2,
        recovered_holdings_count: 1,
        strategy_owned_holdings_count: 1,
        open_orders_count: 1,
        recent_fills_count: 1,
        pending_intents_count: 1,
      },
      balances: [
        {
          asset: "BTC",
          free_qty: 0.01,
          locked_qty: 0,
          total_qty: 0.01,
          source_of_truth: "fixture",
          updated_at_utc: "2026-04-11T12:00:00Z",
        },
      ],
      holdings: [
        {
          account_type: "UNIFIED",
          symbol: "BTCUSDT",
          base_asset: "BTC",
          free_qty: 0.01,
          locked_qty: 0,
          total_qty: 0.01,
          avg_entry_price: 60000,
          hold_reason: "strategy_entry",
          source_of_truth: "fixture",
          recovered_from_exchange: false,
          strategy_owner: "spot_spread",
          auto_sell_allowed: false,
          updated_at_utc: "2026-04-11T12:00:00Z",
        },
      ],
      active_orders: [
        {
          account_type: "UNIFIED",
          symbol: "BTCUSDT",
          side: "Buy",
          order_id: "order-1",
          order_link_id: "link-1",
          order_type: "Limit",
          time_in_force: "PostOnly",
          price: 60000,
          qty: 0.01,
          filled_qty: 0,
          status: "New",
          strategy_owner: "spot_spread",
          updated_at_utc: "2026-04-11T12:00:00Z",
        },
      ],
      recent_fills: [
        {
          account_type: "UNIFIED",
          symbol: "BTCUSDT",
          side: "Buy",
          exec_id: "exec-1",
          order_id: "order-1",
          order_link_id: "link-1",
          price: 60000,
          qty: 0.01,
          fee: 0.02,
          fee_currency: "USDT",
          is_maker: true,
          exec_time_ms: 1700000000123,
          created_at_utc: "2026-04-11T12:00:00Z",
        },
      ],
      truncated: {
        balances: false,
        holdings: false,
        active_orders: false,
        recent_fills: false,
      },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the bounded spot read surface without control actions", async () => {
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
          React.createElement(SpotPage),
        ),
      ),
    );

    expect(await screen.findByRole("heading", { name: "Spot Read Surface" })).toBeTruthy();
    expect((await screen.findByTestId("spot.source-mode")).textContent).toContain("fixture");
    expect((await screen.findByTestId("spot.summary.holdings")).textContent).toContain("2");
    expect(await screen.findByTestId("spot.holding.BTCUSDT")).toBeTruthy();
    expect(await screen.findByTestId("spot.order.BTCUSDT")).toBeTruthy();
    expect(await screen.findByTestId("spot.fill.exec-1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /start|stop|sell|cancel/i })).toBeNull();
  });
});
