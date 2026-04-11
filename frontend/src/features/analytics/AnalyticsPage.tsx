import { AppShell } from "../../shared/ui/AppShell";
import { AnalyticsClosedTradesTable } from "./components/AnalyticsClosedTradesTable";
import { AnalyticsEquityCurveTable } from "./components/AnalyticsEquityCurveTable";
import { AnalyticsSummaryCard } from "./components/AnalyticsSummaryCard";
import { useAnalyticsReadModel } from "./hooks/useAnalyticsReadModel";

function truncatedLabel(value: boolean) {
  return value ? "Showing bounded recent rows." : "Showing all rows in the current bounded snapshot.";
}

export function AnalyticsPage() {
  const analyticsQuery = useAnalyticsReadModel();
  const snapshot = analyticsQuery.data;

  return (
    <AppShell>
      <div className="analytics-layout">
        <section className="panel">
          <h2>PnL / Analytics</h2>
          <p className="panel-muted">
            Read-only summary metrics, bounded cumulative PnL series, and recent closed trades on the new stack.
          </p>
          <p className="status-caption" data-testid="analytics.source-mode">
            Source mode: {snapshot?.source_mode ?? "loading"}
          </p>
        </section>

        {analyticsQuery.isError ? (
          <section className="panel">
            <h2>Analytics Read Error</h2>
            <p className="inline-error" data-testid="analytics.error">
              Failed to load the analytics read model.
            </p>
          </section>
        ) : null}

        <section className="analytics-summary-grid">
          <AnalyticsSummaryCard
            label="Closed Trades"
            value={snapshot?.summary.total_closed_trades ?? "..."}
            note={`Wins: ${snapshot?.summary.winning_trades ?? "..."} | Losses: ${snapshot?.summary.losing_trades ?? "..."}`}
            testId="analytics.summary.closed-trades"
          />
          <AnalyticsSummaryCard
            label="Win Rate"
            value={snapshot ? `${(snapshot.summary.win_rate * 100).toFixed(1)}%` : "..."}
            note="Bounded read-only view over closed-trade outcomes."
            testId="analytics.summary.win-rate"
          />
          <AnalyticsSummaryCard
            label="Total Net PnL"
            value={snapshot?.summary.total_net_pnl?.toFixed(4) ?? "..."}
            note="Aggregate net PnL across the bounded analytics snapshot."
            testId="analytics.summary.total-pnl"
          />
          <AnalyticsSummaryCard
            label="Average Net PnL"
            value={snapshot?.summary.average_net_pnl?.toFixed(4) ?? "..."}
            note="Average closed-trade PnL."
            testId="analytics.summary.avg-pnl"
          />
          <AnalyticsSummaryCard
            label="Today Net PnL"
            value={snapshot?.summary.today_net_pnl?.toFixed(4) ?? "..."}
            note="Today-only contribution from closed trades."
            testId="analytics.summary.today-pnl"
          />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Cumulative PnL Series</h2>
              <p className="panel-muted">{truncatedLabel(snapshot?.truncated.equity_curve ?? false)}</p>
            </div>
          </div>
          <AnalyticsEquityCurveTable points={snapshot?.equity_curve ?? []} />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Recent Closed Trades</h2>
              <p className="panel-muted">{truncatedLabel(snapshot?.truncated.recent_closed_trades ?? false)}</p>
            </div>
          </div>
          <AnalyticsClosedTradesTable trades={snapshot?.recent_closed_trades ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
