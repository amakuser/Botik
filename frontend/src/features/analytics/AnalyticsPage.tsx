import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import { AnalyticsClosedTradesTable } from "./components/AnalyticsClosedTradesTable";
import { AnalyticsEquityCurveTable } from "./components/AnalyticsEquityCurveTable";
import { AnalyticsSummaryCard } from "./components/AnalyticsSummaryCard";
import { useAnalyticsReadModel } from "./hooks/useAnalyticsReadModel";

function truncatedLabel(value: boolean) {
  return value ? "Показаны последние записи (обрезано)." : "Показаны все записи текущего снепшота.";
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
          eyebrow="Данные"
          title="PnL / Аналитика"
          description="Сводные метрики, кривая доходности и последние закрытые сделки."
          meta={
            <>
              <p className="status-caption" data-testid="analytics.source-mode">
                Режим: {snapshot?.source_mode ?? "загрузка"}
              </p>
              <p className="status-caption">Закрытых сделок: {summary?.total_closed_trades ?? "загрузка"}</p>
              <p className="status-caption">Винрейт: {summary ? `${(summary.win_rate * 100).toFixed(1)}%` : "загрузка"}</p>
              <p className="status-caption">
                Последняя точка: {latestPoint ? `${latestPoint.date} / ${latestPoint.cumulative_pnl.toFixed(4)}` : "загрузка"}
              </p>
            </>
          }
        />

        {analyticsQuery.isError ? (
          <section className="panel">
            <h2>Ошибка загрузки аналитики</h2>
            <p className="inline-error" data-testid="analytics.error">
              Не удалось загрузить данные аналитики.
            </p>
          </section>
        ) : null}

        <section className="panel analytics-summary-panel">
          <SectionHeading
            title="Обзор"
            description="Ключевые KPI из текущего снепшота аналитики."
          />
          <div className="analytics-summary-grid">
            <AnalyticsSummaryCard
              eyebrow="Итоги"
              label="Закрытых сделок"
              value={summary?.total_closed_trades ?? "..."}
              note={`Прибыльных: ${summary?.winning_trades ?? "..."} | Убыточных: ${summary?.losing_trades ?? "..."}`}
              testId="analytics.summary.closed-trades"
            />
            <AnalyticsSummaryCard
              eyebrow="Точность"
              label="Винрейт"
              value={summary ? `${(summary.win_rate * 100).toFixed(1)}%` : "..."}
              note="По закрытым сделкам."
              testId="analytics.summary.win-rate"
            />
            <AnalyticsSummaryCard
              eyebrow="Результат"
              label="Суммарный PnL"
              value={summary?.total_net_pnl?.toFixed(4) ?? "..."}
              note="Суммарный чистый PnL по всем закрытым сделкам."
              tone={summary && summary.total_net_pnl >= 0 ? "positive" : "negative"}
              testId="analytics.summary.total-pnl"
            />
            <AnalyticsSummaryCard
              eyebrow="На сделку"
              label="Средний PnL"
              value={summary?.average_net_pnl?.toFixed(4) ?? "..."}
              note="Средний чистый PnL по закрытым сделкам."
              tone={summary && summary.average_net_pnl >= 0 ? "positive" : "negative"}
              testId="analytics.summary.avg-pnl"
            />
            <AnalyticsSummaryCard
              eyebrow="Сегодня"
              label="PnL сегодня"
              value={summary?.today_net_pnl?.toFixed(4) ?? "..."}
              note="Вклад за сегодня от закрытых сделок."
              tone={summary && summary.today_net_pnl >= 0 ? "positive" : "negative"}
              testId="analytics.summary.today-pnl"
            />
          </div>
        </section>

        <section className="panel analytics-series-panel">
          <SectionHeading title="Кривая PnL" description={truncatedLabel(truncated?.equity_curve ?? false)} />
          <div className="analytics-signal-row">
            <div className="runtime-card__signal">
              <span className="runtime-card__signal-label">Последний накопленный</span>
              <strong className={latestPoint && latestPoint.cumulative_pnl < 0 ? "futures-pnl futures-pnl--negative" : "futures-pnl futures-pnl--positive"}>
                {latestPoint ? latestPoint.cumulative_pnl.toFixed(4) : "нет данных"}
              </strong>
              <span className="panel-muted">{latestPoint ? `Дата: ${latestPoint.date}` : "Точек серии нет."}</span>
            </div>
            <div className="runtime-card__signal">
              <span className="runtime-card__signal-label">Последнее дневное изменение</span>
              <strong className={latestPoint && latestPoint.daily_pnl < 0 ? "futures-pnl futures-pnl--negative" : "futures-pnl futures-pnl--positive"}>
                {latestPoint ? latestPoint.daily_pnl.toFixed(4) : "нет данных"}
              </strong>
              <span className="panel-muted">Дневной вклад в текущем снепшоте.</span>
            </div>
          </div>
          <AnalyticsEquityCurveTable points={snapshot?.equity_curve ?? []} />
        </section>

        <section className="panel analytics-trades-panel">
          <SectionHeading title="Последние закрытые сделки" description={truncatedLabel(truncated?.recent_closed_trades ?? false)} />
          <AnalyticsClosedTradesTable trades={snapshot?.recent_closed_trades ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
