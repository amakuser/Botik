import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type { HomeDerivedState } from "../hooks/useHomeDerivedState";
import { SkeletonBox } from "./SkeletonBox";

export interface TradingCardProps {
  derived: HomeDerivedState;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

function formatPnl(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

function pnlClass(value: number): string {
  if (value > 0) return "text-[rgb(var(--token-green))]";
  if (value < 0) return "text-[rgb(var(--token-red))]";
  return "text-[rgb(var(--token-text-primary))]";
}

export function TradingCard({
  derived,
  isLoading,
  isError,
  onRetry,
}: TradingCardProps) {
  const { trading } = derived;
  const cardState =
    trading.runtimesRunning > 0
      ? "ok"
      : trading.runtimesTotal > 0
        ? "idle"
        : "unknown";

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
          {trading.runtimesRunning}/{trading.runtimesTotal} активны
        </span>
      </header>

      <div className="flex items-baseline gap-2">
        <span
          className={cn(
            "text-2xl font-semibold tabular-nums",
            pnlClass(trading.futuresUnrealizedPnl),
          )}
          data-testid="home.trading.pnl"
        >
          {formatPnl(trading.futuresUnrealizedPnl)}
        </span>
        <span className="text-xs text-[rgb(var(--token-text-muted))]">USDT</span>
        <span className="text-[0.7rem] text-[rgb(var(--token-text-muted))]">
          unrealized
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-y-1 text-xs text-[rgb(var(--token-text-secondary))]">
        <dt>Спот холдинги</dt>
        <dd
          className="text-right tabular-nums text-[rgb(var(--token-text-primary))]"
          data-testid="home.trading.spot-holdings"
        >
          {trading.spotHoldings}
        </dd>
        <dt>Фьючерсы поз.</dt>
        <dd
          className="text-right tabular-nums text-[rgb(var(--token-text-primary))]"
          data-testid="home.trading.futures-positions"
        >
          {trading.futuresPositions}
        </dd>
        <dt>Активных ордеров</dt>
        <dd className="text-right tabular-nums text-[rgb(var(--token-text-primary))]">
          {trading.spotOpenOrders + trading.futuresOpenOrders}
        </dd>
      </dl>
    </article>
  );
}
