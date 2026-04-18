import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import { FuturesFillsTable } from "./components/FuturesFillsTable";
import { FuturesOrdersTable } from "./components/FuturesOrdersTable";
import { FuturesPositionsTable } from "./components/FuturesPositionsTable";
import { FuturesSummaryCard } from "./components/FuturesSummaryCard";
import { useFuturesReadModel } from "./hooks/useFuturesReadModel";

function truncatedLabel(value: boolean) {
  return value ? "Показаны последние записи (обрезано)." : "Показаны все записи текущего снепшота.";
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
          eyebrow="Данные"
          title="Фьючерсы"
          description="Открытые позиции, активные ордера, последние сделки и состояние защиты — только чтение."
          meta={
            <>
              <p className="status-caption" data-testid="futures.source-mode">
                Режим: {snapshot?.source_mode ?? "загрузка"}
              </p>
              <p className="status-caption">Аккаунт: {summary?.account_type ?? "загрузка"}</p>
              <p className="status-caption">uPnL: {summary?.unrealized_pnl_total?.toFixed(4) ?? "..."}</p>
            </>
          }
        />

        {futuresQuery.isError ? (
          <section className="panel">
            <h2>Ошибка загрузки фьючерсов</h2>
            <p className="inline-error" data-testid="futures.error">
              Не удалось загрузить данные фьючерсного аккаунта.
            </p>
          </section>
        ) : null}

        <section className="panel futures-summary-panel">
          <SectionHeading title="Снепшот рисков" description="Экспозиция, защита и метрики сверки фьючерсного аккаунта." />
          <div className="futures-summary-grid">
            <FuturesSummaryCard
              label="Открытых позиций"
              value={summary?.positions_count ?? "..."}
              note={`Защищено: ${summary?.protected_positions_count ?? "..."} | Внимание: ${summary?.attention_positions_count ?? "..."}`}
              testId="futures.summary.positions"
            />
            <FuturesSummaryCard
              label="Восстановленных позиций"
              value={summary?.recovered_positions_count ?? "..."}
              note="Позиции, восстановленные из состояния биржи."
              testId="futures.summary.recovered"
            />
            <FuturesSummaryCard
              label="Активных ордеров"
              value={summary?.open_orders_count ?? "..."}
              note="Только открытые фьючерсные ордера."
              testId="futures.summary.orders"
            />
            <FuturesSummaryCard
              label="Последних сделок"
              value={summary?.recent_fills_count ?? "..."}
              note="Только последняя история исполнений."
              testId="futures.summary.fills"
            />
            <FuturesSummaryCard
              label="Суммарный uPnL"
              value={summary?.unrealized_pnl_total?.toFixed(4) ?? "..."}
              note="Нереализованный PnL по всем открытым позициям."
              testId="futures.summary.upnl"
            />
          </div>
        </section>

        <section className="panel">
          <SectionHeading title="Открытые позиции" description={truncatedLabel(truncated?.positions ?? false)} />
          <FuturesPositionsTable positions={snapshot?.positions ?? []} />
        </section>

        <section className="panel">
          <SectionHeading title="Активные ордера" description={truncatedLabel(truncated?.active_orders ?? false)} />
          <FuturesOrdersTable orders={snapshot?.active_orders ?? []} />
        </section>

        <section className="panel">
          <SectionHeading title="Последние сделки" description={truncatedLabel(truncated?.recent_fills ?? false)} />
          <FuturesFillsTable fills={snapshot?.recent_fills ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
