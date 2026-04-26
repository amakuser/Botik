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

  const balancesCount = snapshot?.balances?.length ?? 0;
  const holdingsCount = snapshot?.holdings?.length ?? 0;
  const ordersCount = snapshot?.active_orders?.length ?? 0;
  const fillsCount = snapshot?.recent_fills?.length ?? 0;

  return (
    <AppShell>
      <div className="app-route spot-layout" data-ui-role="page" data-ui-scope="spot">
        <div data-ui-role="spot-intro">
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
        </div>

        {spotQuery.isError ? (
          <section
            className="panel"
            data-ui-role="status-callout"
            data-ui-scope="spot"
            data-ui-kind="error"
          >
            <h2>Ошибка загрузки спота</h2>
            <p className="inline-error" data-testid="spot.error">
              Не удалось загрузить данные спот аккаунта.
            </p>
          </section>
        ) : null}

        <section
          className="panel spot-summary-panel"
          data-ui-role="summary-panel"
          data-ui-scope="spot"
        >
          <SectionHeading title="Снепшот аккаунта" description="Ключевые метрики текущего состояния спот аккаунта." />
          <div className="spot-summary-grid">
            <SpotSummaryCard
              label="Активов на балансе"
              value={summary?.balance_assets_count ?? "..."}
              note="Ненулевые балансы в текущем снепшоте."
              testId="spot.summary.balance-assets"
              uiScope="balance-assets"
            />
            <SpotSummaryCard
              label="Активных холдингов"
              value={summary?.holdings_count ?? "..."}
              note={`Восстановлено: ${summary?.recovered_holdings_count ?? "..."} | Стратегия: ${summary?.strategy_owned_holdings_count ?? "..."}`}
              testId="spot.summary.holdings"
              uiScope="holdings"
            />
            <SpotSummaryCard
              label="Активных ордеров"
              value={summary?.open_orders_count ?? "..."}
              note="Только открытые спот-ордера."
              testId="spot.summary.orders"
              uiScope="orders"
            />
            <SpotSummaryCard
              label="Последних сделок"
              value={summary?.recent_fills_count ?? "..."}
              note="Только последняя история исполнений."
              testId="spot.summary.fills"
              uiScope="fills"
            />
            <SpotSummaryCard
              label="Отложенных интентов"
              value={summary?.pending_intents_count ?? "..."}
              note="Краткая сводка по спот-интентам."
              testId="spot.summary.intents"
              uiScope="intents"
            />
          </div>
        </section>

        <section
          className="panel"
          data-ui-role="history-panel"
          data-ui-scope="balances"
          data-ui-state={balancesCount > 0 ? "populated" : "empty"}
        >
          <SectionHeading title="Балансы" description={truncatedLabel(truncated?.balances ?? false)} />
          <SpotBalancesTable balances={snapshot?.balances ?? []} />
        </section>

        <section
          className="panel"
          data-ui-role="history-panel"
          data-ui-scope="holdings"
          data-ui-state={holdingsCount > 0 ? "populated" : "empty"}
        >
          <SectionHeading title="Холдинги" description={truncatedLabel(truncated?.holdings ?? false)} />
          <SpotHoldingsTable holdings={snapshot?.holdings ?? []} />
        </section>

        <section
          className="panel"
          data-ui-role="history-panel"
          data-ui-scope="active-orders"
          data-ui-state={ordersCount > 0 ? "populated" : "empty"}
        >
          <SectionHeading title="Активные ордера" description={truncatedLabel(truncated?.active_orders ?? false)} />
          <SpotOrdersTable orders={snapshot?.active_orders ?? []} />
        </section>

        <section
          className="panel"
          data-ui-role="history-panel"
          data-ui-scope="recent-fills"
          data-ui-state={fillsCount > 0 ? "populated" : "empty"}
        >
          <SectionHeading title="Последние сделки" description={truncatedLabel(truncated?.recent_fills ?? false)} />
          <SpotFillsTable fills={snapshot?.recent_fills ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
