import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { runTelegramConnectivityCheck } from "../../shared/api/client";
import { AppShell } from "../../shared/ui/AppShell";
import { TelegramConnectivityCheckResult } from "../../shared/contracts";
import { TelegramAlertsTable } from "./components/TelegramAlertsTable";
import { TelegramCommandsTable } from "./components/TelegramCommandsTable";
import { TelegramErrorsTable } from "./components/TelegramErrorsTable";
import { TelegramSummaryCard } from "./components/TelegramSummaryCard";
import { useTelegramOpsModel } from "./hooks/useTelegramOpsModel";

function truncatedLabel(value: boolean) {
  return value ? "Showing bounded recent rows." : "Showing all rows in the current bounded snapshot.";
}

export function TelegramPage() {
  const queryClient = useQueryClient();
  const telegramQuery = useTelegramOpsModel();
  const snapshot = telegramQuery.data;
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
      <div className="telegram-layout">
        <section className="panel">
          <h2>Telegram Ops</h2>
          <p className="panel-muted">
            Read-only operational visibility for Telegram bot configuration, recent alerts, recent errors, and a safe
            connectivity check on the new stack.
          </p>
          <p className="status-caption" data-testid="telegram.source-mode">
            Source mode: {snapshot?.source_mode ?? "loading"}
          </p>
        </section>

        {telegramQuery.isError ? (
          <section className="panel">
            <h2>Telegram Ops Error</h2>
            <p className="inline-error" data-testid="telegram.error.banner">
              Failed to load the Telegram operational view.
            </p>
          </section>
        ) : null}

        <section className="telegram-summary-grid">
          <TelegramSummaryCard
            label="Connectivity"
            value={snapshot?.summary.connectivity_state ?? "..."}
            note={snapshot?.summary.connectivity_detail ?? "Loading connectivity state."}
            testId="telegram.summary.connectivity"
          />
          <TelegramSummaryCard
            label="Allowed Chats"
            value={snapshot?.summary.allowed_chat_count ?? "..."}
            note={(snapshot?.summary.allowed_chats_masked ?? []).join(", ") || "Not configured"}
            testId="telegram.summary.allowed-chats"
          />
          <TelegramSummaryCard
            label="Recent Alerts"
            value={snapshot?.summary.alerts_count ?? "..."}
            note={snapshot?.summary.last_successful_send ?? "No recent alert delivery recorded."}
            testId="telegram.summary.alerts"
          />
          <TelegramSummaryCard
            label="Recent Errors"
            value={snapshot?.summary.errors_count ?? "..."}
            note={snapshot?.summary.last_error ?? "No recent Telegram error observed."}
            testId="telegram.summary.errors"
          />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Connectivity Check</h2>
              <p className="panel-muted">
                Safe `getMe` reachability check only. No message send, no runtime control, no bot mutation.
              </p>
            </div>
            <button
              type="button"
              className="button-secondary"
              onClick={() => void runCheck()}
              disabled={checking}
              data-testid="telegram.connectivity-check"
            >
              {checking ? "Checking..." : "Run Connectivity Check"}
            </button>
          </div>
          {checkResult ? (
            <div className="telegram-check-result" data-testid="telegram.check.result">
              <p className="status-caption">
                State: <strong>{checkResult.state}</strong>
              </p>
              <p className="panel-muted">{checkResult.detail ?? "No additional detail."}</p>
              <p className="panel-muted">
                Bot: {checkResult.bot_username ?? "n/a"} | Latency:{" "}
                {checkResult.latency_ms !== null && checkResult.latency_ms !== undefined ? `${checkResult.latency_ms} ms` : "n/a"}
              </p>
              {checkResult.error ? <p className="inline-error">{checkResult.error}</p> : null}
            </div>
          ) : null}
          {checkError ? (
            <p className="inline-error" data-testid="telegram.check.error">
              {checkError}
            </p>
          ) : null}
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Recent Commands</h2>
              <p className="panel-muted">{truncatedLabel(snapshot?.truncated.recent_commands ?? false)}</p>
            </div>
          </div>
          <TelegramCommandsTable commands={snapshot?.recent_commands ?? []} />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Recent Alerts</h2>
              <p className="panel-muted">{truncatedLabel(snapshot?.truncated.recent_alerts ?? false)}</p>
            </div>
          </div>
          <TelegramAlertsTable alerts={snapshot?.recent_alerts ?? []} />
        </section>

        <section className="panel">
          <div className="surface-panel__header">
            <div>
              <h2>Recent Errors</h2>
              <p className="panel-muted">{truncatedLabel(snapshot?.truncated.recent_errors ?? false)}</p>
            </div>
          </div>
          <TelegramErrorsTable errors={snapshot?.recent_errors ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
