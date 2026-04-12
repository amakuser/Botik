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
  return value ? "Showing bounded recent rows." : "Showing all rows in the current bounded snapshot.";
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
      <div className="app-route telegram-layout">
        <PageIntro
          eyebrow="Operations"
          title="Telegram Ops"
          description="Bounded operational visibility for Telegram health, recent alerts, recent errors, and a safe connectivity check on the primary stack."
          meta={
            <>
              <p className="status-caption" data-testid="telegram.source-mode">
                Source mode: {snapshot?.source_mode ?? "loading"}
              </p>
              <p className="status-caption">Bot profile: {summary?.bot_profile ?? "loading"}</p>
              <p className="status-caption">Startup: {summary?.startup_status ?? "loading"}</p>
              <p className="status-caption">Connectivity: {summary?.connectivity_state ?? "loading"}</p>
            </>
          }
        />

        {telegramQuery.isError ? (
          <section className="panel">
            <h2>Telegram Ops Error</h2>
            <p className="inline-error" data-testid="telegram.error.banner">
              Failed to load the Telegram operational view.
            </p>
          </section>
        ) : null}

        <section className="panel telegram-summary-panel">
          <SectionHeading
            title="Overview"
            description="Current bot availability, chat binding, and recent delivery health across the bounded Telegram operations snapshot."
          />
          <div className="telegram-summary-grid">
            <TelegramSummaryCard
              eyebrow="Connection"
              label="Connectivity"
              value={summary?.connectivity_state ?? "..."}
              note={summary?.connectivity_detail ?? "Loading connectivity state."}
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
            />
            <TelegramSummaryCard
              eyebrow="Bindings"
              label="Allowed Chats"
              value={summary?.allowed_chat_count ?? "..."}
              note={(summary?.allowed_chats_masked ?? []).join(", ") || "Not configured"}
              testId="telegram.summary.allowed-chats"
            />
            <TelegramSummaryCard
              eyebrow="Delivery"
              label="Recent Alerts"
              value={summary?.alerts_count ?? "..."}
              note={summary?.last_successful_send ?? "No recent alert delivery recorded."}
              testId="telegram.summary.alerts"
            />
            <TelegramSummaryCard
              eyebrow="Warnings"
              label="Recent Errors"
              value={summary?.errors_count ?? "..."}
              note={summary?.last_error ?? "No recent Telegram error observed."}
              tone={summary && summary.errors_count > 0 ? "negative" : "positive"}
              testId="telegram.summary.errors"
            />
          </div>
        </section>

        <section className="panel telegram-connectivity-panel">
          <SectionHeading
            title="Connectivity Check"
            description="Safe `getMe` reachability check only. No message send, no runtime control, no bot mutation."
            actions={
              <button
                type="button"
                className="button-secondary"
                onClick={() => void runCheck()}
                disabled={checking}
                data-testid="telegram.connectivity-check"
              >
                {checking ? "Checking..." : "Run Connectivity Check"}
              </button>
            }
          />
          <div className="telegram-ops-signals">
            <div className="runtime-card__signal">
              <span className="runtime-card__signal-label">Bot state</span>
              <strong>{summary?.connectivity_state ?? "loading"}</strong>
              <span className="panel-muted">{summary?.connectivity_detail ?? "No connectivity detail yet."}</span>
            </div>
            <div className="runtime-card__signal">
              <span className="runtime-card__signal-label">Token / startup</span>
              <strong>{summary ? (summary.token_configured ? "configured" : "missing") : "loading"}</strong>
              <span className="panel-muted">
                {summary?.token_profile_name ?? "loading"} · {summary?.startup_status ?? "loading"}
              </span>
            </div>
            <div className="runtime-card__signal">
              <span className="runtime-card__signal-label">Chat binding</span>
              <strong>{summary?.allowed_chat_count ?? "loading"}</strong>
              <span className="panel-muted">{(summary?.allowed_chats_masked ?? []).join(", ") || "No chats configured"}</span>
            </div>
          </div>
          {checkResult ? (
            <div className="telegram-check-result runtime-card__callout" data-testid="telegram.check.result">
              <p className="runtime-card__callout-label">Latest check result</p>
              <p className="runtime-card__reason">
                State: <strong>{checkResult.state}</strong>
              </p>
              <p className="panel-muted">{checkResult.detail ?? "No additional detail."}</p>
              <div className="telegram-check-result__meta">
                <span className="surface-badge">Bot: {checkResult.bot_username ?? "n/a"}</span>
                <span className="surface-badge surface-badge--soft">
                  Latency: {checkResult.latency_ms !== null && checkResult.latency_ms !== undefined ? `${checkResult.latency_ms} ms` : "n/a"}
                </span>
                <span className="surface-badge">Source: {checkResult.source_mode}</span>
              </div>
              {checkResult.error ? <p className="inline-error">{checkResult.error}</p> : null}
            </div>
          ) : null}
          {checkError ? (
            <div className="runtime-card__callout runtime-card__callout--error">
              <p className="runtime-card__callout-label">Connectivity check error</p>
              <p className="inline-error" data-testid="telegram.check.error">
                {checkError}
              </p>
            </div>
          ) : null}
        </section>

        <section className="panel telegram-history-panel">
          <SectionHeading title="Recent Commands" description={truncatedLabel(truncated?.recent_commands ?? false)} />
          <TelegramCommandsTable commands={snapshot?.recent_commands ?? []} />
        </section>

        <section className="panel telegram-history-panel">
          <SectionHeading title="Recent Alerts" description={truncatedLabel(truncated?.recent_alerts ?? false)} />
          <TelegramAlertsTable alerts={snapshot?.recent_alerts ?? []} />
        </section>

        <section className="panel telegram-history-panel">
          <SectionHeading title="Recent Errors" description={truncatedLabel(truncated?.recent_errors ?? false)} />
          <TelegramErrorsTable errors={snapshot?.recent_errors ?? []} />
        </section>
      </div>
    </AppShell>
  );
}
