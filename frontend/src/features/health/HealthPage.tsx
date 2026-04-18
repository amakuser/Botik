import { useQuery } from "@tanstack/react-query";
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
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
  testId?: string;
}) {
  return (
    <article className="home-metric-card panel" data-testid={testId}>
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
}: {
  step: number;
  title: string;
  description: string;
  state: PipelineState;
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
    running: "Active",
    idle: "Idle",
    unknown: "Unknown",
  };

  return (
    <div className="pipeline-step panel">
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
      <div className="app-route home-layout">
        <PageIntro
          eyebrow="Overview"
          title="Foundation Health"
          description="Primary stack health, live trading metrics, and pipeline status."
          meta={
            <>
              <p data-testid="health.status">Health: {health.isLoading ? "loading" : (health.data?.status ?? "unavailable")}</p>
              <p data-testid="health.service">Service: {health.data?.service ?? "n/a"}</p>
              <p data-testid="health.version">Version: {health.data?.version ?? "n/a"}</p>
            </>
          }
        />

        {/* Metric cards */}
        <div className="home-metrics-grid">
          <MetricCard
            label="PnL Today"
            value={(todayPnl !== undefined ? (todayPnl >= 0 ? "+" : "") : "") + fmt(todayPnl) + " USDT"}
            sub={`Total: ${fmt(totalPnl, "+")} USDT`}
            color={pnlColor(todayPnl)}
            testId="home.metric.pnl-today"
          />
          <MetricCard
            label="USDT Balance"
            value={usdtBalance !== undefined ? fmt(usdtBalance) + " USDT" : "—"}
            sub="Spot account"
            testId="home.metric.balance"
          />
          <MetricCard
            label="Trades (Total)"
            value={String(tradeCount)}
            sub={winRate !== undefined ? `Win rate: ${fmt(winRate)}%` : undefined}
            testId="home.metric.trades"
          />
          <MetricCard
            label="Open Positions"
            value={String(openPositions)}
            sub={`Spot ${spotHoldings} · Futures ${futuresPosCount}`}
            testId="home.metric.positions"
          />
        </div>

        {/* Pipeline */}
        <section className="panel">
          <SectionHeading
            title="Pipeline"
            description="Data → Models → Trading — current status of each stage."
          />
          <div className="pipeline-grid">
            <PipelineStep
              step={1}
              title="Historical Data"
              description="OHLCV candles for training and backtesting."
              state="unknown"
            />
            <PipelineStep
              step={2}
              title="ML Models"
              description={`${readyScopes} of 2 scopes ready (Spot / Futures).`}
              state={modelsState}
            />
            <PipelineStep
              step={3}
              title="Live Trading"
              description={anyRunning ? `${runtimeList.filter((r) => r.state === "running").length} runtime(s) active.` : "All runtimes idle."}
              state={tradingState}
            />
          </div>
        </section>

        {/* Bootstrap (collapsed) */}
        <section className="panel" aria-labelledby="foundation-bootstrap-title">
          <SectionHeading
            title="Bootstrap"
            description="App-service session details and registered routes."
          />
          <p data-testid="bootstrap.app-name" style={{ marginTop: 0 }}>
            App: {bootstrap.isLoading ? "loading" : (bootstrap.data?.app_name ?? "n/a")}
          </p>
          <p data-testid="bootstrap.session-id">
            Session: {bootstrap.data?.session.session_id ?? "n/a"}
          </p>
          <p data-testid="bootstrap.routes" style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
            Routes: {bootstrap.data?.routes.join(", ") ?? "n/a"}
          </p>
        </section>
      </div>
    </AppShell>
  );
}
