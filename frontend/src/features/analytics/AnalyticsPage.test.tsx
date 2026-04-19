import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AnalyticsPage } from "./AnalyticsPage";

vi.mock("./hooks/useAnalyticsReadModel", () => ({
  useAnalyticsReadModel: () => ({
    isError: false,
    data: {
      source_mode: "fixture",
      summary: {
        total_closed_trades: 4,
        winning_trades: 3,
        losing_trades: 1,
        win_rate: 0.75,
        total_net_pnl: 15.5,
        average_net_pnl: 3.875,
        today_net_pnl: 2.5,
      },
      equity_curve: [
        { date: "2026-04-08", daily_pnl: 5.0, cumulative_pnl: 5.0 },
        { date: "2026-04-09", daily_pnl: 10.5, cumulative_pnl: 15.5 },
      ],
      recent_closed_trades: [
        { symbol: "BTCUSDT", scope: "spot", net_pnl: 5.0, was_profitable: true, closed_at: "2026-04-09 12:00" },
      ],
      truncated: {
        equity_curve: false,
        recent_closed_trades: false,
      },
    },
  }),
}));

describe("AnalyticsPage", () => {
  it("renders the bounded analytics snapshot", async () => {
    const queryClient = new QueryClient();

    render(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          React.createElement(AnalyticsPage),
        ),
      ),
    );

    expect(screen.getByRole("heading", { name: "PnL / Аналитика" })).toBeTruthy();
    expect(screen.getByTestId("analytics.source-mode").textContent).toContain("fixture");
    expect(screen.getByTestId("analytics.summary.closed-trades").textContent).toContain("4");
    expect(screen.getByTestId("analytics.summary.total-pnl").textContent).toContain("15.5000");
    expect(screen.getByTestId("analytics.equity.2026-04-09")).toBeTruthy();
    expect(screen.getByTestId("analytics.trade.0").textContent).toContain("BTCUSDT");
  });
});
