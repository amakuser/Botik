import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import { FuturesFillsTable } from "./components/FuturesFillsTable";
import { FuturesOrdersTable } from "./components/FuturesOrdersTable";
import { FuturesPositionsTable } from "./components/FuturesPositionsTable";
import { FuturesSummaryCard } from "./components/FuturesSummaryCard";
import { useFuturesReadModel } from "./hooks/useFuturesReadModel";

function truncatedLabel(value: boolean) {
  return value ? "Showing bounded recent rows." : "Showing all rows in the current bounded snapshot.";
}

export function FuturesPage() {
  const futuresQuery = useFuturesReadModel();
  const snapshot = futuresQuery.data;
  const summary = snapshot?.summary;
  const truncated = snapshot?.truncated;

  return (
    <AppShell>
      <div className="app-route futures-layout">
        <PageIntro
          eyebrow="Read Surface"
          title="Futures Read Surface"
          description="Bounded read-only visibility for open positions, active orders, recent fills, and protection state on the primary stack."
          meta={
            <p className="status-caption" data-testid="futures.source-mode">
              Source mode: {snapshot?.source_mode ?? "loading"}
            </p>
          }
        />

        {futuresQuery.isError ? (
          <section className="panel">
            <h2>Futures Read Error</h2>
            <p className="inline-error" data-testid="futures.error">
              Failed to load the futures read model.
            </p>
          </section>
        ) : null}

        <section className="futures-summary-grid">
          <FuturesSummaryCard
            label="Open Positions"
            value={summary?.positions_count ?? "..."}
            note={`Protected: ${summary?.protected_positions_count ?? "..."} | Attention: ${summary?.attention_positions_count ?? "..."}`}
            testId="futures.summary.positions"
          />
          <FuturesSummaryCard
            label="Recovered Positions"
            value={summary?.recovered_positions_count ?? "..."}
            note="Recovered futures positions from exchange state."
            testId="futures.summary.recovered"
          />
          <FuturesSummaryCard
            label="Active Orders"
            value={summary?.open_orders_count ?? "..."}
            note="Open futures orders only."
            testId="futures.summary.orders"
          />
          <FuturesSummaryCard
            label="Recent Fills"
            value={summary?.recent_fills_count ?? "..."}
            note="Recent futures execution history only."
            testId="futures.summary.fills"
          />
          <FuturesSummaryCard
            label="Total uPnL"
            value={summary?.unrealized_pnl_total?.toFixed(4) ?? "..."}
            note="Aggregated unrealized PnL for currently open positions."
            testId="futures.summary.upnl"
          />
        </section>

        <section className="panel">
          <SectionHeading title="Open Positions" description={truncatedLabel(truncated?.positions ?? false)} />
          <FuturesPositionsTable positions={snapshot?.positions ?? []} />
        </section>

        <section className="panel">
          <SectionHeading title="Active Orders" description={truncatedLabel(truncated?.active_orders ?? false)} />
          <FuturesOrdersTable orders={snapshot?.active_orders ?? []} />
        </section>

        <section className="panel">
          <SectionHeading title="Recent Fills" description={truncatedLabel(truncated?.recent_fills ?? false)} />
          <FuturesFillsTable fills={snapshot?.recent_fills ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
