import { useMemo } from "react";
import type {
  DiagnosticsSnapshot,
  FuturesPosition,
  FuturesReadSnapshot,
  ModelsReadSnapshot,
  RuntimeStatusSnapshot,
  SpotReadSnapshot,
  TelegramOpsSnapshot,
} from "../../../shared/contracts";
import type { HomeData, HomeErrors } from "./useHomeData";

export const GLOBAL_STATE = {
  HEALTHY: "HEALTHY",
  WARNING: "WARNING",
  CRITICAL: "CRITICAL",
} as const;
export type GlobalState = (typeof GLOBAL_STATE)[keyof typeof GLOBAL_STATE];

export type SubsystemState = "ok" | "warning" | "critical" | "unknown";

export interface SubsystemStatus {
  key: string;
  label: string;
  state: SubsystemState;
  detail: string | null;
}

export interface ProtectionAggregate {
  total: number;
  protected: number;
  attention: number;
  unprotected: number;
  failed: number;
  pending: number;
  positions: FuturesPosition[];
}

export interface ReconciliationStatus {
  state: "ok" | "stale" | "failed" | "unavailable";
  detail: string | null;
}

export interface MlPipelineStatus {
  state: "ok" | "warning" | "error" | "idle";
  readyScopes: number;
  totalScopes: number;
  latestRunStatus: string;
  detail: string | null;
}

export interface ConnectionStatus {
  bybit: SubsystemState;
  telegram: SubsystemState;
  db: SubsystemState;
  bybitDetail: string | null;
  telegramDetail: string | null;
  dbDetail: string | null;
}

export interface PrimaryAction {
  label: string;
  kind: string;
  href?: string;
}

export interface GlobalSummary {
  state: GlobalState;
  health_score: number;
  critical_reason: string | null;
  primary_action: PrimaryAction | null;
}

export interface HomeDerivedState {
  global: GlobalSummary;
  subsystems: SubsystemStatus[];
  protection: ProtectionAggregate;
  reconciliation: ReconciliationStatus;
  mlPipeline: MlPipelineStatus;
  connections: ConnectionStatus;
  trading: {
    spotHoldings: number;
    futuresPositions: number;
    futuresUnrealizedPnl: number;
    spotOpenOrders: number;
    futuresOpenOrders: number;
    runtimesRunning: number;
    runtimesTotal: number;
  };
  hasAnyData: boolean;
}

const PROTECTION_PENDING_STALE_SECONDS = 60;

function lower(value: string | null | undefined): string {
  return (value ?? "").toLowerCase();
}

export function classifyProtection(
  positions: FuturesPosition[] | undefined,
): ProtectionAggregate {
  const list = positions ?? [];
  let protectedCount = 0;
  let attention = 0;
  let unprotected = 0;
  let failed = 0;
  let pending = 0;

  for (const pos of list) {
    const status = lower(pos.protection_status);
    if (status === "protected") protectedCount += 1;
    else if (status === "attention") attention += 1;
    else if (status === "unprotected") unprotected += 1;
    else if (status === "failed") failed += 1;
    else if (status === "pending") pending += 1;
  }

  return {
    total: list.length,
    protected: protectedCount,
    attention,
    unprotected,
    failed,
    pending,
    positions: list,
  };
}

function ageSecondsFromIso(iso: string | null | undefined, now: number): number | null {
  if (!iso) return null;
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return null;
  return Math.max(0, (now - parsed) / 1000);
}

function classifyBybit(
  runtime: RuntimeStatusSnapshot | undefined,
  errors: HomeErrors,
): { state: SubsystemState; detail: string | null } {
  if (errors.runtime) {
    return { state: "critical", detail: "Не удалось получить статус рантайма" };
  }
  if (!runtime) {
    return { state: "unknown", detail: null };
  }
  const runtimes = runtime.runtimes ?? [];
  if (runtimes.length === 0) {
    return { state: "unknown", detail: "Рантаймы не зарегистрированы" };
  }
  const hasError = runtimes.some((r) => r.last_error && r.last_error.length > 0);
  const anyDegraded = runtimes.some((r) => r.state === "degraded");
  const allOffline = runtimes.every((r) => r.state === "offline");
  if (hasError) {
    return {
      state: "critical",
      detail: runtimes.find((r) => r.last_error)?.last_error ?? "Ошибка коннектора Bybit",
    };
  }
  if (anyDegraded) {
    return { state: "warning", detail: "Один или несколько рантаймов в degraded" };
  }
  if (allOffline) {
    return { state: "ok", detail: "Все рантаймы остановлены" };
  }
  return { state: "ok", detail: null };
}

function classifyTelegram(
  telegram: TelegramOpsSnapshot | undefined,
  errors: HomeErrors,
): { state: SubsystemState; detail: string | null } {
  if (errors.telegram) {
    return { state: "warning", detail: "Не удалось получить ops Telegram" };
  }
  if (!telegram) return { state: "unknown", detail: null };
  const summary = telegram.summary;
  const tokenConfigured = summary?.token_configured ?? false;
  const internalDisabled = summary?.internal_bot_disabled ?? false;
  const recentErrors = telegram.recent_errors ?? [];
  if (!tokenConfigured) {
    return { state: "warning", detail: "Telegram-токен не настроен" };
  }
  if (internalDisabled) {
    return { state: "warning", detail: "Внутренний бот отключен" };
  }
  if (recentErrors.length > 0) {
    return { state: "warning", detail: `Последние ошибки: ${recentErrors.length}` };
  }
  return { state: "ok", detail: null };
}

function classifyDb(
  diagnostics: DiagnosticsSnapshot | undefined,
  models: ModelsReadSnapshot | undefined,
  errors: HomeErrors,
): { state: SubsystemState; detail: string | null } {
  if (errors.diagnostics && errors.models) {
    return { state: "warning", detail: "Диагностика и модели недоступны" };
  }
  if (!diagnostics && !models) return { state: "unknown", detail: null };
  const dbAvailable = models?.summary?.db_available;
  const missingPaths = diagnostics?.summary?.missing_paths_count ?? 0;
  const warnings = diagnostics?.summary?.warnings_count ?? 0;
  if (dbAvailable === false) {
    return { state: "warning", detail: "БД моделей недоступна" };
  }
  if (missingPaths > 0) {
    return { state: "warning", detail: `Отсутствует путей: ${missingPaths}` };
  }
  if (warnings > 0) {
    return { state: "warning", detail: `Предупреждений: ${warnings}` };
  }
  return { state: "ok", detail: null };
}

function classifyMlPipeline(
  models: ModelsReadSnapshot | undefined,
  errors: HomeErrors,
): MlPipelineStatus {
  if (errors.models) {
    return {
      state: "error",
      readyScopes: 0,
      totalScopes: 0,
      latestRunStatus: "ошибка",
      detail: "Не удалось загрузить состояние моделей",
    };
  }
  if (!models) {
    return {
      state: "idle",
      readyScopes: 0,
      totalScopes: 0,
      latestRunStatus: "загрузка",
      detail: null,
    };
  }
  const summary = models.summary;
  const scopes = models.scopes ?? [];
  const readyScopes = summary?.ready_scopes ?? scopes.filter((s) => s.ready).length;
  const totalScopes = scopes.length;
  const latestRunStatus = lower(summary?.latest_run_status ?? "");
  if (latestRunStatus.includes("fail") || latestRunStatus.includes("error")) {
    return {
      state: "error",
      readyScopes,
      totalScopes,
      latestRunStatus: summary?.latest_run_status ?? "ошибка",
      detail: "Последний training run завершился с ошибкой",
    };
  }
  if (readyScopes === 0 && totalScopes > 0) {
    return {
      state: "warning",
      readyScopes,
      totalScopes,
      latestRunStatus: summary?.latest_run_status ?? "—",
      detail: "Нет готовых scope-ов",
    };
  }
  if (totalScopes > 0 && readyScopes < totalScopes) {
    return {
      state: "warning",
      readyScopes,
      totalScopes,
      latestRunStatus: summary?.latest_run_status ?? "—",
      detail: `Готов ${readyScopes} из ${totalScopes}`,
    };
  }
  return {
    state: "ok",
    readyScopes,
    totalScopes,
    latestRunStatus: summary?.latest_run_status ?? "—",
    detail: null,
  };
}

function classifyReconciliation(
  diagnostics: DiagnosticsSnapshot | undefined,
  errors: HomeErrors,
  now: number,
): ReconciliationStatus {
  if (errors.diagnostics) {
    return { state: "failed", detail: "Не удалось получить diagnostics" };
  }
  if (!diagnostics) return { state: "unavailable", detail: null };
  const generated = diagnostics.generated_at;
  const age = ageSecondsFromIso(generated, now);
  // Бэкенд не отдаёт явный reconciliation timestamp; используем generated_at
  // диагностики как нижнюю границу свежести и warnings_count как индикатор.
  const warnings = diagnostics.summary?.warnings_count ?? 0;
  if (warnings > 0) {
    return { state: "stale", detail: `Предупреждений: ${warnings}` };
  }
  if (age !== null && age > 600) {
    return { state: "stale", detail: `Снепшот старше ${Math.round(age)}s` };
  }
  return { state: "ok", detail: null };
}

function classifyTrading(
  spot: SpotReadSnapshot | undefined,
  futures: FuturesReadSnapshot | undefined,
  runtime: RuntimeStatusSnapshot | undefined,
) {
  const spotHoldings = spot?.summary?.holdings_count ?? 0;
  const futuresPositions = futures?.summary?.positions_count ?? 0;
  const futuresUnrealizedPnl = futures?.summary?.unrealized_pnl_total ?? 0;
  const spotOpenOrders = spot?.summary?.open_orders_count ?? 0;
  const futuresOpenOrders = futures?.summary?.open_orders_count ?? 0;
  const runtimes = runtime?.runtimes ?? [];
  const runtimesRunning = runtimes.filter((r) => r.state === "running").length;
  const runtimesTotal = runtimes.length;
  return {
    spotHoldings,
    futuresPositions,
    futuresUnrealizedPnl,
    spotOpenOrders,
    futuresOpenOrders,
    runtimesRunning,
    runtimesTotal,
  };
}

interface DeriveOptions {
  now?: number;
}

export function deriveHomeState(
  data: HomeData,
  errors: HomeErrors,
  options: DeriveOptions = {},
): HomeDerivedState {
  const now = options.now ?? Date.now();

  const protection = classifyProtection(data.futures?.positions);
  const bybit = classifyBybit(data.runtime, errors);
  const telegram = classifyTelegram(data.telegram, errors);
  const db = classifyDb(data.diagnostics, data.models, errors);
  const ml = classifyMlPipeline(data.models, errors);
  const reconciliation = classifyReconciliation(data.diagnostics, errors, now);
  const trading = classifyTrading(data.spot, data.futures, data.runtime);

  // Pending protection age: используем generated_at futures snapshot как proxy.
  const futuresGenerated = ageSecondsFromIso(data.futures?.generated_at ?? null, now);
  const pendingStale =
    protection.pending > 0 &&
    futuresGenerated !== null &&
    futuresGenerated > PROTECTION_PENDING_STALE_SECONDS;

  // Critical conditions
  const reasons: string[] = [];
  if (protection.unprotected > 0) {
    reasons.push(`${protection.unprotected} незащищённых позиций`);
  }
  if (protection.failed > 0) {
    reasons.push(`${protection.failed} позиций с ошибкой защиты`);
  }
  if (bybit.state === "critical") {
    reasons.push(bybit.detail ?? "Ошибка соединения с Bybit");
  }
  if (reconciliation.state === "failed") {
    reasons.push(reconciliation.detail ?? "Reconciliation failed");
  }

  // Warning conditions
  const warnings: string[] = [];
  if (bybit.state === "warning") warnings.push(bybit.detail ?? "Bybit degraded");
  if (telegram.state === "warning") warnings.push(telegram.detail ?? "Telegram degraded");
  if (db.state === "warning") warnings.push(db.detail ?? "DB degraded");
  if (ml.state === "error") warnings.push(ml.detail ?? "ML pipeline error");
  if (ml.state === "warning") warnings.push(ml.detail ?? "ML pipeline warning");
  if (reconciliation.state === "stale") {
    warnings.push(reconciliation.detail ?? "Reconciliation stale");
  }
  if (pendingStale) {
    warnings.push("Защита позиций задерживается > 60s");
  }

  const isCritical = reasons.length > 0;
  const isWarning = !isCritical && warnings.length > 0;

  const globalState: GlobalState = isCritical
    ? GLOBAL_STATE.CRITICAL
    : isWarning
      ? GLOBAL_STATE.WARNING
      : GLOBAL_STATE.HEALTHY;

  // Score: -30 per critical, -15 per warning, -5 per pending stale, -10 per stale reconciliation.
  let score = 100;
  // Critical subsystems
  if (protection.unprotected > 0 || protection.failed > 0) score -= 30;
  if (bybit.state === "critical") score -= 30;
  if (reconciliation.state === "failed") score -= 30;
  // Warning subsystems
  if (bybit.state === "warning") score -= 15;
  if (telegram.state === "warning") score -= 15;
  if (db.state === "warning") score -= 15;
  if (ml.state === "error") score -= 15;
  if (ml.state === "warning") score -= 15;
  if (pendingStale) score -= 5;
  if (reconciliation.state === "stale") score -= 10;
  if (score < 0) score = 0;
  if (score > 100) score = 100;

  let primaryAction: PrimaryAction | null = null;
  if (isCritical) {
    if (protection.unprotected > 0 || protection.failed > 0) {
      primaryAction = {
        label: "Открыть позиции",
        kind: "open-futures",
        href: "/futures",
      };
    } else if (bybit.state === "critical") {
      primaryAction = {
        label: "Перейти в рантайм",
        kind: "open-runtime",
        href: "/runtime",
      };
    } else {
      primaryAction = {
        label: "Открыть диагностику",
        kind: "open-diagnostics",
        href: "/diagnostics",
      };
    }
  }

  const subsystems: SubsystemStatus[] = [
    {
      key: "trading",
      label: "Торговля",
      state:
        trading.runtimesRunning > 0 ? "ok" : trading.runtimesTotal > 0 ? "warning" : "unknown",
      detail:
        trading.runtimesTotal === 0
          ? "Нет рантаймов"
          : `${trading.runtimesRunning}/${trading.runtimesTotal} активны`,
    },
    {
      key: "protection",
      label: "Защита позиций",
      state:
        protection.unprotected > 0 || protection.failed > 0
          ? "critical"
          : protection.attention > 0 || protection.pending > 0
            ? "warning"
            : "ok",
      detail:
        protection.total === 0
          ? "Нет открытых позиций"
          : `${protection.protected}/${protection.total} защищены`,
    },
    {
      key: "reconciliation",
      label: "Reconciliation",
      state:
        reconciliation.state === "failed"
          ? "critical"
          : reconciliation.state === "stale"
            ? "warning"
            : reconciliation.state === "unavailable"
              ? "unknown"
              : "ok",
      detail: reconciliation.detail,
    },
    {
      key: "ml",
      label: "ML Pipeline",
      state:
        ml.state === "error" ? "critical" : ml.state === "warning" ? "warning" : "ok",
      detail: ml.detail,
    },
    {
      key: "bybit",
      label: "Bybit",
      state: bybit.state,
      detail: bybit.detail,
    },
    {
      key: "telegram",
      label: "Telegram",
      state: telegram.state,
      detail: telegram.detail,
    },
    {
      key: "db",
      label: "База данных",
      state: db.state,
      detail: db.detail,
    },
  ];

  const hasAnyData =
    data.health !== undefined ||
    data.runtime !== undefined ||
    data.spot !== undefined ||
    data.futures !== undefined ||
    data.models !== undefined ||
    data.telegram !== undefined ||
    data.diagnostics !== undefined ||
    data.jobs !== undefined;

  const criticalReason = reasons[0] ?? null;

  return {
    global: {
      state: globalState,
      health_score: Math.round(score),
      critical_reason: criticalReason,
      primary_action: primaryAction,
    },
    subsystems,
    protection,
    reconciliation,
    mlPipeline: ml,
    connections: {
      bybit: bybit.state,
      telegram: telegram.state,
      db: db.state,
      bybitDetail: bybit.detail,
      telegramDetail: telegram.detail,
      dbDetail: db.detail,
    },
    trading,
    hasAnyData,
  };
}

export function useHomeDerivedState(
  data: HomeData,
  errors: HomeErrors,
): HomeDerivedState {
  return useMemo(() => deriveHomeState(data, errors), [data, errors]);
}
