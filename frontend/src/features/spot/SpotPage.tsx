import { AppShell } from "../../shared/ui/AppShell";
import { SpotBalancesTable } from "./components/SpotBalancesTable";
import { SpotFillsTable } from "./components/SpotFillsTable";
import { SpotHoldingsTable } from "./components/SpotHoldingsTable";
import { SpotOrdersTable } from "./components/SpotOrdersTable";
import { SpotSummaryCard } from "./components/SpotSummaryCard";
import { useSpotReadModel } from "./hooks/useSpotReadModel";

function truncatedLabel(value: boolean) {
  return value ? "Showing bounded recent rows." : "Showing all rows in the current bounded snapshot.";
}

export function SpotPage() {
  const spotQuery = useSpotReadModel();
  const snapshot = spotQuery.data;
  const summary = snapshot?.summary;
  const truncated = snapshot?.truncated;

  return (
    <AppShell>
      <div className="spot-layout">
        <section className="panel">
          <h2>Spot Read Surface</h2>
          <p className="panel-muted">
            Read-only visibility for balances, holdings, active orders, and recent fills on the new stack.
          </p>
          <p className="status-caption" data-testid="spot.source-mode">
            Source mode: {snapshot?.source_mode ?? "loading"}
          </p>
        </section>

        {spotQuery.isError ? (
          <section className="panel">
            <h2>Spot Read Error</h2>
            <p className="inline-error" data-testid="spot.error">
              Failed to load the spot read model.
            </p>
          </section>
        ) : null}

        <section className="spot-summary-grid">
          <SpotSummaryCard
            label="Balance Assets"
            value={summary?.balance_assets_count ?? "..."}
            note="Non-zero spot balances in the current account snapshot."
            testId="spot.summary.balance-assets"
          />
          <SpotSummaryCard
            label="Active Holdings"
            value={summary?.holdings_count ?? "..."}
            note={`Recovered: ${summary?.recovered_holdings_count ?? "..."} | Strategy-owned: ${summary?.strategy_owned_holdings_count ?? "..."}`}
            testId="spot.summary.holdings"
          />
          <SpotSummaryCard
            label="Active Orders"
            value={summary?.open_orders_count ?? "..."}
            note="Open spot orders only."
            testId="spot.summary.orders"
          />
          <SpotSummaryCard
            label="Recent Fills"
            value={summary?.recent_fills_count ?? "..."}
            note="Recent execution history only."
            testId="spot.summary.fills"
          />
          <SpotSummaryCard
            label="Pending Intents"
            value={summary?.pending_intents_count ?? "..."}
            note="Minimal intent summary from existing spot intent data."
            testId="spot.summary.intents"
          />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Balances</h2>
              <p className="panel-muted">{truncatedLabel(truncated?.balances ?? false)}</p>
            </div>
          </div>
          <SpotBalancesTable balances={snapshot?.balances ?? []} />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Holdings</h2>
              <p className="panel-muted">{truncatedLabel(truncated?.holdings ?? false)}</p>
            </div>
          </div>
          <SpotHoldingsTable holdings={snapshot?.holdings ?? []} />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Active Orders</h2>
              <p className="panel-muted">{truncatedLabel(truncated?.active_orders ?? false)}</p>
            </div>
          </div>
          <SpotOrdersTable orders={snapshot?.active_orders ?? []} />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Recent Fills</h2>
              <p className="panel-muted">{truncatedLabel(truncated?.recent_fills ?? false)}</p>
            </div>
          </div>
          <SpotFillsTable fills={snapshot?.recent_fills ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
