import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import { SpotBalancesTable } from "./components/SpotBalancesTable";
import { SpotFillsTable } from "./components/SpotFillsTable";
import { SpotHoldingsTable } from "./components/SpotHoldingsTable";
import { SpotOrdersTable } from "./components/SpotOrdersTable";
import { SpotSummaryCard } from "./components/SpotSummaryCard";
import { useSpotReadModel } from "./hooks/useSpotReadModel";

function truncatedLabel(value: boolean) {
  return value ? "Показаны последние записи (обрезано)." : "Показаны все записи текущего снепшота.";
}

export function SpotPage() {
  const spotQuery = useSpotReadModel();
  const snapshot = spotQuery.data;
  const summary = snapshot?.summary;
  const truncated = snapshot?.truncated;

  return (
    <AppShell>
      <div className="app-route spot-layout">
        <PageIntro
          eyebrow="Данные"
          title="Спот"
          description="Балансы, холдинги, активные ордера и последние сделки — только чтение."
          meta={
            <>
              <p className="status-caption" data-testid="spot.source-mode">
                Режим: {snapshot?.source_mode ?? "загрузка"}
              </p>
              <p className="status-caption">Аккаунт: {summary?.account_type ?? "загрузка"}</p>
              <p className="status-caption">Открытых ордеров: {summary?.open_orders_count ?? "..."}</p>
            </>
          }
        />

        {spotQuery.isError ? (
          <section className="panel">
            <h2>Ошибка загрузки спота</h2>
            <p className="inline-error" data-testid="spot.error">
              Не удалось загрузить данные спот аккаунта.
            </p>
          </section>
        ) : null}

        <section className="panel spot-summary-panel">
          <SectionHeading title="Снепшот аккаунта" description="Ключевые метрики текущего состояния спот аккаунта." />
          <div className="spot-summary-grid">
            <SpotSummaryCard
              label="Активов на балансе"
              value={summary?.balance_assets_count ?? "..."}
              note="Ненулевые балансы в текущем снепшоте."
              testId="spot.summary.balance-assets"
            />
            <SpotSummaryCard
              label="Активных холдингов"
              value={summary?.holdings_count ?? "..."}
              note={`Восстановлено: ${summary?.recovered_holdings_count ?? "..."} | Стратегия: ${summary?.strategy_owned_holdings_count ?? "..."}`}
              testId="spot.summary.holdings"
            />
            <SpotSummaryCard
              label="Активных ордеров"
              value={summary?.open_orders_count ?? "..."}
              note="Только открытые спот-ордера."
              testId="spot.summary.orders"
            />
            <SpotSummaryCard
              label="Последних сделок"
              value={summary?.recent_fills_count ?? "..."}
              note="Только последняя история исполнений."
              testId="spot.summary.fills"
            />
            <SpotSummaryCard
              label="Отложенных интентов"
              value={summary?.pending_intents_count ?? "..."}
              note="Краткая сводка по спот-интентам."
              testId="spot.summary.intents"
            />
          </div>
        </section>

        <section className="panel">
          <SectionHeading title="Балансы" description={truncatedLabel(truncated?.balances ?? false)} />
          <SpotBalancesTable balances={snapshot?.balances ?? []} />
        </section>

        <section className="panel">
          <SectionHeading title="Холдинги" description={truncatedLabel(truncated?.holdings ?? false)} />
          <SpotHoldingsTable holdings={snapshot?.holdings ?? []} />
        </section>

        <section className="panel">
          <SectionHeading title="Активные ордера" description={truncatedLabel(truncated?.active_orders ?? false)} />
          <SpotOrdersTable orders={snapshot?.active_orders ?? []} />
        </section>

        <section className="panel">
          <SectionHeading title="Последние сделки" description={truncatedLabel(truncated?.recent_fills ?? false)} />
          <SpotFillsTable fills={snapshot?.recent_fills ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
