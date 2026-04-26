import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type {
  HomeRuntimeState,
  TradingBlock,
} from "../../../shared/contracts";
import { SkeletonBox } from "./SkeletonBox";
import { StatusDot } from "./StatusDot";

export interface TradingCardProps {
  trading: TradingBlock;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

const RUNTIME_DOT: Record<HomeRuntimeState, "ok" | "warning" | "critical" | "unknown"> = {
  running: "ok",
  degraded: "warning",
  offline: "critical",
  unknown: "unknown",
};

const RUNTIME_LABEL: Record<HomeRuntimeState, string> = {
  running: "running",
  degraded: "degraded",
  offline: "offline",
  unknown: "unknown",
};

function formatPnl(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

function pnlClass(trend: "up" | "down" | "flat"): string {
  if (trend === "up") return "text-[rgb(var(--token-green))]";
  if (trend === "down") return "text-[rgb(var(--token-red))]";
  return "text-[rgb(var(--token-text-primary))]";
}

function cardStateFromTrading(t: TradingBlock): "ok" | "idle" | "unknown" {
  const states: HomeRuntimeState[] = [t.spot.state, t.futures.state];
  if (states.includes("running")) return "ok";
  if (states.some((s) => s === "degraded" || s === "offline")) return "idle";
  return "unknown";
}

export function TradingCard({
  trading,
  isLoading,
  isError,
  onRetry,
}: TradingCardProps) {
  const cardState = cardStateFromTrading(trading);

  if (isError) {
    return (
      <article
        data-ui-role="trading-card"
        data-ui-scope="home"
        data-ui-state="error"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <header className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
            Торговля
          </h3>
        </header>
        <p className="text-xs text-[rgb(var(--token-red))]">
          Не удалось загрузить торговые данные.
        </p>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRetry}
          data-testid="home.trading.retry"
        >
          Повторить
        </Button>
      </article>
    );
  }

  if (isLoading) {
    return (
      <article
        data-ui-role="trading-card"
        data-ui-scope="home"
        data-ui-state="loading"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <SkeletonBox scope="trading-card" width="40%" height="0.9rem" />
        <SkeletonBox scope="trading-card" width="70%" height="1.5rem" />
        <SkeletonBox scope="trading-card" width="55%" height="0.8rem" />
      </article>
    );
  }

  const pnl = trading.today_pnl;

  return (
    <article
      data-ui-role="trading-card"
      data-ui-scope="home"
      data-ui-state={cardState}
      className={cn(
        "panel rounded-xl border p-4 flex flex-col gap-2",
        "border-white/10 transition-colors duration-300",
      )}
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Торговля
        </h3>
        <span className="text-[0.7rem] uppercase tracking-wide text-[rgb(var(--token-text-muted))]">
          PnL за сегодня
        </span>
      </header>

      <div className="flex items-baseline gap-2">
        {pnl ? (
          <>
            <span
              className={cn(
                "text-2xl font-semibold tabular-nums",
                pnlClass(pnl.trend),
              )}
              data-testid="home.trading.pnl"
            >
              {formatPnl(pnl.value)}
            </span>
            <span className="text-xs text-[rgb(var(--token-text-muted))]">
              {pnl.currency}
            </span>
          </>
        ) : (
          <span
            className="text-base text-[rgb(var(--token-text-muted))]"
            data-testid="home.trading.pnl"
          >
            Недоступно
          </span>
        )}
      </div>

      <ul className="flex flex-col gap-1 text-xs text-[rgb(var(--token-text-secondary))]">
        <li className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <StatusDot state={RUNTIME_DOT[trading.spot.state]} size="sm" />
            <span>Spot</span>
          </span>
          <span
            className="text-right tabular-nums text-[rgb(var(--token-text-primary))]"
            data-testid="home.trading.spot-state"
          >
            {RUNTIME_LABEL[trading.spot.state]}
          </span>
        </li>
        <li className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <StatusDot state={RUNTIME_DOT[trading.futures.state]} size="sm" />
            <span>Futures</span>
          </span>
          <span
            className="text-right tabular-nums text-[rgb(var(--token-text-primary))]"
            data-testid="home.trading.futures-state"
          >
            {RUNTIME_LABEL[trading.futures.state]}
          </span>
        </li>
      </ul>
    </article>
  );
}
