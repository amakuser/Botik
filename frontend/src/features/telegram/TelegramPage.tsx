import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { runTelegramConnectivityCheck } from "../../shared/api/client";
import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import { TelegramConnectivityCheckResult } from "../../shared/contracts";
import { TelegramAlertsTable } from "./components/TelegramAlertsTable";
import { TelegramCommandsTable } from "./components/TelegramCommandsTable";
import { TelegramErrorsTable } from "./components/TelegramErrorsTable";
import { TelegramSummaryCard } from "./components/TelegramSummaryCard";
import { useTelegramOpsModel } from "./hooks/useTelegramOpsModel";

function truncatedLabel(value: boolean) {
  return value ? "Показаны последние записи (обрезано)." : "Показаны все записи текущего снепшота.";
}

export function TelegramPage() {
  const queryClient = useQueryClient();
  const telegramQuery = useTelegramOpsModel();
  const snapshot = telegramQuery.data;
  const summary = snapshot?.summary;
  const truncated = snapshot?.truncated;
  const [checkResult, setCheckResult] = useState<TelegramConnectivityCheckResult | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function runCheck() {
    setChecking(true);
    setCheckError(null);
    try {
      const result = await runTelegramConnectivityCheck();
      setCheckResult(result);
      await queryClient.invalidateQueries({ queryKey: ["telegram-ops-model"] });
    } catch (error) {
      setCheckError(error instanceof Error ? error.message : "Failed to run Telegram connectivity check.");
    } finally {
      setChecking(false);
    }
  }

  return (
    <AppShell>
      <div className="app-route telegram-layout" data-ui-role="page" data-ui-scope="telegram">
        <div data-ui-role="telegram-intro">
          <PageIntro
            eyebrow="Операции"
            title="Телеграм"
            description="Состояние Telegram бота, алерты, ошибки и проверка подключения."
            meta={
              <>
                <p className="status-caption" data-testid="telegram.source-mode">
                  Режим: {snapshot?.source_mode ?? "загрузка"}
                </p>
                <p className="status-caption">Профиль бота: {summary?.bot_profile ?? "загрузка"}</p>
                <p className="status-caption">Запуск: {summary?.startup_status ?? "загрузка"}</p>
                <p className="status-caption">Связь: {summary?.connectivity_state ?? "загрузка"}</p>
              </>
            }
          />
        </div>

        {telegramQuery.isError ? (
          <section className="panel" data-ui-role="status-callout" data-ui-scope="telegram" data-ui-kind="error">
            <h2>Ошибка Telegram</h2>
            <p className="inline-error" data-testid="telegram.error.banner">
              Не удалось загрузить данные Telegram.
            </p>
          </section>
        ) : null}

        <section className="panel telegram-summary-panel" data-ui-role="summary-panel" data-ui-scope="telegram">
          <SectionHeading
            title="Обзор"
            description="Доступность бота, привязка чатов и статус доставки сообщений."
          />
          <div className="telegram-summary-grid">
            <TelegramSummaryCard
              eyebrow="Подключение"
              label="Состояние связи"
              value={summary?.connectivity_state ?? "..."}
              note={summary?.connectivity_detail ?? "Загрузка состояния связи."}
              tone={
                summary?.connectivity_state === "healthy"
                  ? "positive"
                  : summary?.connectivity_state === "degraded" ||
                      summary?.connectivity_state === "missing_token" ||
                      summary?.connectivity_state === "disabled"
                    ? "negative"
                    : "neutral"
              }
              testId="telegram.summary.connectivity"
              uiScope="connectivity"
            />
            <TelegramSummaryCard
              eyebrow="Привязки"
              label="Разрешённые чаты"
              value={summary?.allowed_chat_count ?? "..."}
              note={(summary?.allowed_chats_masked ?? []).join(", ") || "Не настроено"}
              testId="telegram.summary.allowed-chats"
              uiScope="allowed-chats"
            />
            <TelegramSummaryCard
              eyebrow="Доставка"
              label="Последних алертов"
              value={summary?.alerts_count ?? "..."}
              note={summary?.last_successful_send ?? "Доставленных алертов нет."}
              testId="telegram.summary.alerts"
              uiScope="alerts"
            />
            <TelegramSummaryCard
              eyebrow="Предупреждения"
              label="Последних ошибок"
              value={summary?.errors_count ?? "..."}
              note={summary?.last_error ?? "Ошибок Telegram не обнаружено."}
              tone={summary && summary.errors_count > 0 ? "negative" : "positive"}
              testId="telegram.summary.errors"
              uiScope="errors"
            />
          </div>
        </section>

        <section className="panel telegram-connectivity-panel" data-ui-role="connectivity-panel" data-ui-scope="telegram">
          <SectionHeading
            title="Проверка связи"
            description="Безопасная проверка доступности (`getMe`). Без отправки сообщений и изменений."
            actions={
              <button
                type="button"
                className="button-secondary"
                onClick={() => void runCheck()}
                disabled={checking}
                data-testid="telegram.connectivity-check"
                data-ui-role="connectivity-action"
                data-ui-scope="check"
                data-ui-action="run"
                data-ui-state={checking ? "disabled" : "enabled"}
              >
                {checking ? "Проверяю..." : "Проверить связь"}
              </button>
            }
          />
          <div className="telegram-ops-signals">
            <div className="runtime-card__signal" data-ui-role="connectivity-signal" data-ui-scope="bot">
              <span className="runtime-card__signal-label">Состояние бота</span>
              <strong>{summary?.connectivity_state ?? "загрузка"}</strong>
              <span className="panel-muted">{summary?.connectivity_detail ?? "Нет данных о связи."}</span>
            </div>
            <div className="runtime-card__signal" data-ui-role="connectivity-signal" data-ui-scope="token">
              <span className="runtime-card__signal-label">Токен / запуск</span>
              <strong>{summary ? (summary.token_configured ? "настроен" : "отсутствует") : "загрузка"}</strong>
              <span className="panel-muted">
                {summary?.token_profile_name ?? "загрузка"} · {summary?.startup_status ?? "загрузка"}
              </span>
            </div>
            <div className="runtime-card__signal" data-ui-role="connectivity-signal" data-ui-scope="chats">
              <span className="runtime-card__signal-label">Привязка чатов</span>
              <strong>{summary?.allowed_chat_count ?? "загрузка"}</strong>
              <span className="panel-muted">{(summary?.allowed_chats_masked ?? []).join(", ") || "Чаты не настроены"}</span>
            </div>
          </div>
          {checkResult ? (
            <div className="telegram-check-result runtime-card__callout" data-testid="telegram.check.result" data-ui-role="status-callout" data-ui-scope="connectivity-result" data-ui-kind="info">
              <p className="runtime-card__callout-label">Результат последней проверки</p>
              <p className="runtime-card__reason">
                Статус: <strong>{checkResult.state}</strong>
              </p>
              <p className="panel-muted">{checkResult.detail ?? "Нет дополнительных данных."}</p>
              <div className="telegram-check-result__meta">
                <span className="surface-badge">Бот: {checkResult.bot_username ?? "n/a"}</span>
                <span className="surface-badge surface-badge--soft">
                  Задержка: {checkResult.latency_ms !== null && checkResult.latency_ms !== undefined ? `${checkResult.latency_ms} ms` : "n/a"}
                </span>
                <span className="surface-badge">Источник: {checkResult.source_mode}</span>
              </div>
              {checkResult.error ? <p className="inline-error">{checkResult.error}</p> : null}
            </div>
          ) : null}
          {checkError ? (
            <div className="runtime-card__callout runtime-card__callout--error" data-ui-role="status-callout" data-ui-scope="connectivity-result" data-ui-kind="error">
              <p className="runtime-card__callout-label">Ошибка проверки связи</p>
              <p className="inline-error" data-testid="telegram.check.error">
                {checkError}
              </p>
            </div>
          ) : null}
        </section>

        <section className="panel telegram-history-panel" data-ui-role="history-panel" data-ui-scope="commands" data-ui-state={(snapshot?.recent_commands?.length ?? 0) > 0 ? "populated" : "empty"}>
          <SectionHeading title="Последние команды" description={truncatedLabel(truncated?.recent_commands ?? false)} />
          <TelegramCommandsTable commands={snapshot?.recent_commands ?? []} />
        </section>

        <section className="panel telegram-history-panel" data-ui-role="history-panel" data-ui-scope="alerts" data-ui-state={(snapshot?.recent_alerts?.length ?? 0) > 0 ? "populated" : "empty"}>
          <SectionHeading title="Последние алерты" description={truncatedLabel(truncated?.recent_alerts ?? false)} />
          <TelegramAlertsTable alerts={snapshot?.recent_alerts ?? []} />
        </section>

        <section className="panel telegram-history-panel" data-ui-role="history-panel" data-ui-scope="errors" data-ui-state={(snapshot?.recent_errors?.length ?? 0) > 0 ? "populated" : "empty"}>
          <SectionHeading title="Последние ошибки" description={truncatedLabel(truncated?.recent_errors ?? false)} />
          <TelegramErrorsTable errors={snapshot?.recent_errors ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
