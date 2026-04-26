import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { fadeIn, staggerContainer, staggerItem } from "../../styles/motion";
import { getBootstrap, getHealth, getAnalyticsReadModel, getSpotReadModel, getFuturesReadModel, getRuntimeStatus, getModelsReadModel } from "../../shared/api/client";
import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";

function MetricCard({
  label,
  value,
  sub,
  color,
  testId,
  uiScope,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
  testId?: string;
  uiScope: string;
}) {
  return (
    <article className="home-metric-card panel" data-testid={testId} data-ui-role="metric-card" data-ui-scope={uiScope}>
      <p className="home-metric-card__label">{label}</p>
      <strong className="home-metric-card__value" style={{ color: color ?? "var(--text-primary)" }}>
        {value}
      </strong>
      {sub ? <p className="home-metric-card__sub">{sub}</p> : null}
    </article>
  );
}

function pnlColor(val: number | undefined): string {
  if (val === undefined) return "var(--text-primary)";
  return val > 0 ? "#86efac" : val < 0 ? "#fca5a5" : "var(--text-primary)";
}

function fmt(n: number | undefined, prefix = ""): string {
  if (n === undefined) return "—";
  const s = n.toFixed(2);
  return n > 0 && prefix === "+" ? `+${s}` : s;
}

type PipelineState = "running" | "idle" | "unknown";

function PipelineStep({
  step,
  title,
  description,
  state,
  uiScope,
}: {
  step: number;
  title: string;
  description: string;
  state: PipelineState;
  uiScope: string;
}) {
  const colors: Record<PipelineState, string> = {
    running: "#86efac",
    idle: "var(--text-muted)",
    unknown: "var(--text-muted)",
  };
  const dots: Record<PipelineState, string> = {
    running: "#22c55e",
    idle: "rgba(201,209,220,0.28)",
    unknown: "rgba(201,209,220,0.18)",
  };
  const labels: Record<PipelineState, string> = {
    running: "Активно",
    idle: "Остановлен",
    unknown: "Неизвестно",
  };

  return (
    <div className="pipeline-step panel" data-ui-role="pipeline-step" data-ui-scope={uiScope} data-ui-state={state}>
      <div className="pipeline-step__header">
        <span className="pipeline-step__num">{step}</span>
        <span
          className="pipeline-step__dot"
          style={{ background: dots[state] }}
          title={labels[state]}
        />
      </div>
      <p className="pipeline-step__title">{title}</p>
      <p className="pipeline-step__desc">{description}</p>
      <p className="pipeline-step__state" style={{ color: colors[state] }}>
        {labels[state]}
      </p>
    </div>
  );
}

export function HealthPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth });
  const bootstrap = useQuery({ queryKey: ["bootstrap"], queryFn: getBootstrap });
  const analytics = useQuery({
    queryKey: ["analytics-read-model"],
    queryFn: getAnalyticsReadModel,
    refetchInterval: 10_000,
  });
  const spot = useQuery({
    queryKey: ["spot-read-model"],
    queryFn: getSpotReadModel,
    refetchInterval: 10_000,
  });
  const futures = useQuery({
    queryKey: ["futures-read-model"],
    queryFn: getFuturesReadModel,
    refetchInterval: 10_000,
  });
  const runtimes = useQuery({
    queryKey: ["runtime-status"],
    queryFn: getRuntimeStatus,
    refetchInterval: 5_000,
  });
  const models = useQuery({
    queryKey: ["models-read-model"],
    queryFn: getModelsReadModel,
    refetchInterval: 15_000,
  });

  const summary = analytics.data?.summary;
  const todayPnl = summary?.today_net_pnl;
  const totalPnl = summary?.total_net_pnl;
  const tradeCount = summary?.total_closed_trades ?? 0;
  const winRate = summary?.win_rate;
  const spotHoldings = spot.data?.summary?.holdings_count ?? 0;
  const futuresPosCount = futures.data?.summary?.positions_count ?? 0;
  const openPositions = spotHoldings + futuresPosCount;

  const usdtBalance = spot.data?.balances?.find((b) => b.asset === "USDT")?.total_qty;

  // Pipeline states
  const runtimeList = runtimes.data?.runtimes ?? [];
  const anyRunning = runtimeList.some((r) => r.state === "running");
  const tradingState: PipelineState = anyRunning ? "running" : runtimes.data ? "idle" : "unknown";

  const readyScopes = models.data?.summary?.ready_scopes ?? 0;
  const modelsState: PipelineState = readyScopes > 0 ? "running" : models.data ? "idle" : "unknown";

  return (
    <AppShell>
      <motion.div className="app-route home-layout" {...fadeIn} data-ui-role="page" data-ui-scope="health">
        <div data-ui-role="health-intro">
          <PageIntro
            eyebrow="Обзор"
            title="Состояние системы"
            description="Здоровье стека, метрики торговли в реальном времени и статус пайплайна."
            meta={
              <>
                <p data-testid="health.status">Статус: {health.isLoading ? "загрузка" : (health.data?.status ?? "недоступен")}</p>
                <p data-testid="health.service">Сервис: {health.data?.service ?? "n/a"}</p>
                <p data-testid="health.version">Версия: {health.data?.version ?? "n/a"}</p>
              </>
            }
          />
        </div>

        {/* Metric cards */}
        <motion.div
          className="home-metrics-grid"
          variants={staggerContainer}
          initial="initial"
          animate="animate"
        >
          <motion.div variants={staggerItem}>
            <MetricCard
              label="PnL сегодня"
              value={(todayPnl !== undefined ? (todayPnl >= 0 ? "+" : "") : "") + fmt(todayPnl) + " USDT"}
              sub={`Всего: ${fmt(totalPnl, "+")} USDT`}
              color={pnlColor(todayPnl)}
              testId="home.metric.pnl-today"
              uiScope="pnl-today"
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <MetricCard
              label="Баланс USDT"
              value={usdtBalance !== undefined ? fmt(usdtBalance) + " USDT" : "—"}
              sub="Спот аккаунт"
              testId="home.metric.balance"
              uiScope="balance"
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <MetricCard
              label="Сделок (всего)"
              value={String(tradeCount)}
              sub={winRate !== undefined ? `Винрейт: ${fmt(winRate)}%` : undefined}
              testId="home.metric.trades"
              uiScope="trades"
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <MetricCard
              label="Открытых позиций"
              value={String(openPositions)}
              sub={`Спот ${spotHoldings} · Фьючерсы ${futuresPosCount}`}
              testId="home.metric.positions"
              uiScope="positions"
            />
          </motion.div>
        </motion.div>

        {/* Pipeline */}
        <section className="panel" data-ui-role="pipeline" data-ui-scope="health">
          <SectionHeading
            title="Пайплайн"
            description="Данные → Модели → Торговля — текущий статус каждого этапа."
          />
          <div className="pipeline-grid">
            <PipelineStep
              step={1}
              title="Исторические данные"
              description="OHLCV свечи для обучения и бэктеста."
              state="unknown"
              uiScope="historical-data"
            />
            <PipelineStep
              step={2}
              title="ML Модели"
              description={`${readyScopes} из 2 скоупов готово (Spot / Futures).`}
              state={modelsState}
              uiScope="ml-models"
            />
            <PipelineStep
              step={3}
              title="Торговля"
              description={anyRunning ? `${runtimeList.filter((r) => r.state === "running").length} рантайм(ов) активно.` : "Все рантаймы остановлены."}
              state={tradingState}
              uiScope="trading"
            />
          </div>
        </section>

        {/* Bootstrap (collapsed) */}
        <section className="panel" aria-labelledby="foundation-bootstrap-title" data-ui-role="bootstrap" data-ui-scope="session">
          <SectionHeading
            title="Bootstrap"
            description="Детали сессии сервиса и зарегистрированные маршруты."
          />
          <p data-testid="bootstrap.app-name" style={{ marginTop: 0 }}>
            Приложение: {bootstrap.isLoading ? "загрузка" : (bootstrap.data?.app_name ?? "n/a")}
          </p>
          <p data-testid="bootstrap.session-id">
            Сессия: {bootstrap.data?.session.session_id ?? "n/a"}
          </p>
          <p data-testid="bootstrap.routes" style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
            Маршруты: {bootstrap.data?.routes.join(", ") ?? "n/a"}
          </p>
        </section>
      </motion.div>
    </AppShell>
  );
}
