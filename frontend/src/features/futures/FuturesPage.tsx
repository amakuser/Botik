import { AppShell } from "../../shared/ui/AppShell";
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
      <div className="futures-layout">
        <section className="panel">
          <h2>Futures Read Surface</h2>
          <p className="panel-muted">
            Read-only visibility for open positions, active orders, recent fills, and protection state on the new stack.
          </p>
          <p className="status-caption" data-testid="futures.source-mode">
            Source mode: {snapshot?.source_mode ?? "loading"}
          </p>
        </section>

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
          <div className="surface-panel__header">
            <div>
              <h2>Open Positions</h2>
              <p className="panel-muted">{truncatedLabel(truncated?.positions ?? false)}</p>
            </div>
          </div>
          <FuturesPositionsTable positions={snapshot?.positions ?? []} />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Active Orders</h2>
              <p className="panel-muted">{truncatedLabel(truncated?.active_orders ?? false)}</p>
            </div>
          </div>
          <FuturesOrdersTable orders={snapshot?.active_orders ?? []} />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Recent Fills</h2>
              <p className="panel-muted">{truncatedLabel(truncated?.recent_fills ?? false)}</p>
            </div>
          </div>
          <FuturesFillsTable fills={snapshot?.recent_fills ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
