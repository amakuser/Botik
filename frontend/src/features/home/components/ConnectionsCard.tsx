import { Button } from "../../../shared/ui/primitives/Button";
import { cn } from "../../../shared/lib/utils";
import type {
  ConnectionsBlock,
  DbHealthState,
} from "../../../shared/contracts";
import { SkeletonBox } from "./SkeletonBox";
import { StatusDot } from "./StatusDot";

export interface ConnectionsCardProps {
  connections: ConnectionsBlock;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}

type DotState = "ok" | "warning" | "critical" | "unknown";

const DB_DOT: Record<DbHealthState, DotState> = {
  ok: "ok",
  degraded: "warning",
  unavailable: "critical",
};

const DB_LABEL: Record<DbHealthState, string> = {
  ok: "OK",
  degraded: "Деградация",
  unavailable: "Недоступно",
};

interface RowProps {
  label: string;
  state: DotState;
  text: string;
}

function Row({ label, state, text }: RowProps) {
  return (
    <li className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2">
        <StatusDot state={state} size="sm" />
        <span className="text-[rgb(var(--token-text-primary))]">{label}</span>
      </div>
      <div className="flex flex-col items-end text-right">
        <span className="text-xs text-[rgb(var(--token-text-secondary))]">
          {text}
        </span>
      </div>
    </li>
  );
}

function overallState(db: DbHealthState): DotState {
  // bybit and telegram are always null → unknown — they never push the
  // overall card past the database signal in this slice.
  if (db === "unavailable") return "critical";
  if (db === "degraded") return "warning";
  return "ok";
}

export function ConnectionsCard({
  connections,
  isLoading,
  isError,
  onRetry,
}: ConnectionsCardProps) {
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

  const overall = overallState(connections.database);

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
        <Row label="Bybit" state="unknown" text="Недоступно" />
        <Row label="Telegram" state="unknown" text="Недоступно" />
        <Row
          label="База данных"
          state={DB_DOT[connections.database]}
          text={DB_LABEL[connections.database]}
        />
      </ul>
    </article>
  );
}
