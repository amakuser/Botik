import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type {
  HomeDerivedState,
  SubsystemState,
} from "../hooks/useHomeDerivedState";
import { SkeletonBox } from "./SkeletonBox";
import { StatusDot } from "./StatusDot";

export interface ConnectionsCardProps {
  derived: HomeDerivedState;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

const DOT_STATE: Record<SubsystemState, "ok" | "warning" | "critical" | "unknown"> = {
  ok: "ok",
  warning: "warning",
  critical: "critical",
  unknown: "unknown",
};

const STATE_LABEL: Record<SubsystemState, string> = {
  ok: "OK",
  warning: "Внимание",
  critical: "Сбой",
  unknown: "—",
};

interface RowProps {
  label: string;
  state: SubsystemState;
  detail: string | null;
}

function Row({ label, state, detail }: RowProps) {
  return (
    <li className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2">
        <StatusDot state={DOT_STATE[state]} size="sm" />
        <span className="text-[rgb(var(--token-text-primary))]">{label}</span>
      </div>
      <div className="flex flex-col items-end text-right">
        <span className="text-xs text-[rgb(var(--token-text-secondary))]">
          {STATE_LABEL[state]}
        </span>
        {detail ? (
          <span className="text-[0.7rem] text-[rgb(var(--token-text-muted))]">
            {detail}
          </span>
        ) : null}
      </div>
    </li>
  );
}

function worstState(states: SubsystemState[]): SubsystemState {
  if (states.includes("critical")) return "critical";
  if (states.includes("warning")) return "warning";
  if (states.includes("unknown") && !states.includes("ok")) return "unknown";
  return "ok";
}

export function ConnectionsCard({
  derived,
  isLoading,
  isError,
  onRetry,
}: ConnectionsCardProps) {
  const c = derived.connections;
  const overall = worstState([c.bybit, c.telegram, c.db]);

  if (isError) {
    return (
      <article
        data-ui-role="connections-card"
        data-ui-scope="home"
        data-ui-state="error"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Соединения
        </h3>
        <p className="text-xs text-[rgb(var(--token-red))]">
          Не удалось получить состояние соединений.
        </p>
        <Button variant="ghost" size="sm" onClick={onRetry}>
          Повторить
        </Button>
      </article>
    );
  }

  if (isLoading) {
    return (
      <article
        data-ui-role="connections-card"
        data-ui-scope="home"
        data-ui-state="loading"
        className="panel rounded-xl border border-white/10 p-4 flex flex-col gap-3"
      >
        <SkeletonBox scope="connections-card" width="50%" height="0.9rem" />
        <SkeletonBox scope="connections-card" width="100%" height="2.5rem" />
      </article>
    );
  }

  return (
    <article
      data-ui-role="connections-card"
      data-ui-scope="home"
      data-ui-state={overall}
      className={cn(
        "panel rounded-xl border p-4 flex flex-col gap-3",
        "border-white/10 transition-colors duration-300",
      )}
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-[rgb(var(--token-text-primary))]">
          Соединения
        </h3>
      </header>
      <ul className="flex flex-col gap-2">
        <Row label="Bybit" state={c.bybit} detail={c.bybitDetail} />
        <Row label="Telegram" state={c.telegram} detail={c.telegramDetail} />
        <Row label="База данных" state={c.db} detail={c.dbDetail} />
      </ul>
    </article>
  );
}
