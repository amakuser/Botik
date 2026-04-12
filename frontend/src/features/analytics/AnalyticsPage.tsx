import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
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
  const summary = snapshot?.summary;
  const truncated = snapshot?.truncated;
  const latestPoint = snapshot?.equity_curve ? snapshot.equity_curve.at(-1) : undefined;

  return (
    <AppShell>
      <div className="app-route analytics-layout">
        <PageIntro
          eyebrow="Read Surface"
          title="PnL / Analytics"
          description="Bounded read-only summary metrics, cumulative performance series, and recent closed trades on the primary stack."
          meta={
            <>
              <p className="status-caption" data-testid="analytics.source-mode">
                Source mode: {snapshot?.source_mode ?? "loading"}
              </p>
              <p className="status-caption">Closed trades: {summary?.total_closed_trades ?? "loading"}</p>
              <p className="status-caption">Win rate: {summary ? `${(summary.win_rate * 100).toFixed(1)}%` : "loading"}</p>
              <p className="status-caption">
                Latest series point: {latestPoint ? `${latestPoint.date} / ${latestPoint.cumulative_pnl.toFixed(4)}` : "loading"}
              </p>
            </>
          }
        />

        {analyticsQuery.isError ? (
          <section className="panel">
            <h2>Analytics Read Error</h2>
            <p className="inline-error" data-testid="analytics.error">
              Failed to load the analytics read model.
            </p>
          </section>
        ) : null}

        <section className="panel analytics-summary-panel">
          <SectionHeading
            title="Overview"
            description="Headline KPIs from the current bounded analytics snapshot, with emphasis on readiness, freshness, and recent performance."
          />
          <div className="analytics-summary-grid">
            <AnalyticsSummaryCard
              eyebrow="Outcomes"
              label="Closed Trades"
              value={summary?.total_closed_trades ?? "..."}
              note={`Wins: ${summary?.winning_trades ?? "..."} | Losses: ${summary?.losing_trades ?? "..."}`}
              testId="analytics.summary.closed-trades"
            />
            <AnalyticsSummaryCard
              eyebrow="Hit Rate"
              label="Win Rate"
              value={summary ? `${(summary.win_rate * 100).toFixed(1)}%` : "..."}
              note="Bounded read-only view over closed-trade outcomes."
              testId="analytics.summary.win-rate"
            />
            <AnalyticsSummaryCard
              eyebrow="Performance"
              label="Total Net PnL"
              value={summary?.total_net_pnl?.toFixed(4) ?? "..."}
              note="Aggregate net PnL across the bounded analytics snapshot."
              tone={summary && summary.total_net_pnl >= 0 ? "positive" : "negative"}
              testId="analytics.summary.total-pnl"
            />
            <AnalyticsSummaryCard
              eyebrow="Per Trade"
              label="Average Net PnL"
              value={summary?.average_net_pnl?.toFixed(4) ?? "..."}
              note="Average closed-trade PnL."
              tone={summary && summary.average_net_pnl >= 0 ? "positive" : "negative"}
              testId="analytics.summary.avg-pnl"
            />
            <AnalyticsSummaryCard
              eyebrow="Today"
              label="Today Net PnL"
              value={summary?.today_net_pnl?.toFixed(4) ?? "..."}
              note="Today-only contribution from closed trades."
              tone={summary && summary.today_net_pnl >= 0 ? "positive" : "negative"}
              testId="analytics.summary.today-pnl"
            />
          </div>
        </section>

        <section className="panel analytics-series-panel">
          <SectionHeading title="Cumulative PnL Series" description={truncatedLabel(truncated?.equity_curve ?? false)} />
          <div className="analytics-signal-row">
            <div className="runtime-card__signal">
              <span className="runtime-card__signal-label">Latest cumulative</span>
              <strong className={latestPoint && latestPoint.cumulative_pnl < 0 ? "futures-pnl futures-pnl--negative" : "futures-pnl futures-pnl--positive"}>
                {latestPoint ? latestPoint.cumulative_pnl.toFixed(4) : "not available"}
              </strong>
              <span className="panel-muted">{latestPoint ? `Series date: ${latestPoint.date}` : "No series points available yet."}</span>
            </div>
            <div className="runtime-card__signal">
              <span className="runtime-card__signal-label">Latest daily change</span>
              <strong className={latestPoint && latestPoint.daily_pnl < 0 ? "futures-pnl futures-pnl--negative" : "futures-pnl futures-pnl--positive"}>
                {latestPoint ? latestPoint.daily_pnl.toFixed(4) : "not available"}
              </strong>
              <span className="panel-muted">Bounded daily contribution in the current snapshot.</span>
            </div>
          </div>
          <AnalyticsEquityCurveTable points={snapshot?.equity_curve ?? []} />
        </section>

        <section className="panel analytics-trades-panel">
          <SectionHeading title="Recent Closed Trades" description={truncatedLabel(truncated?.recent_closed_trades ?? false)} />
          <AnalyticsClosedTradesTable trades={snapshot?.recent_closed_trades ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
