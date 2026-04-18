import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { runBacktest } from "../../shared/api/client";
import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import type { BacktestRunResult, BacktestTrade } from "../../shared/contracts";

const SCOPES = ["futures", "spot"] as const;
const INTERVALS = [
  { value: "1", label: "1m" },
  { value: "5", label: "5m" },
  { value: "15", label: "15m" },
  { value: "60", label: "1h" },
];
const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT"];

function MetricCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bt-metric">
      <p className="bt-metric__label">{label}</p>
      <strong className="bt-metric__value" style={{ color: color ?? "var(--text-primary)" }}>
        {value}
      </strong>
    </div>
  );
}

function pnlColor(val: number): string {
  return val > 0 ? "#86efac" : val < 0 ? "#fca5a5" : "var(--text-primary)";
}

function fmt(n: number, d = 2): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

function TradesTable({ trades }: { trades: BacktestTrade[] }) {
  if (trades.length === 0) {
    return <p className="panel-muted">No trades executed in this period.</p>;
  }
  return (
    <div className="surface-table-wrap">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Opened</th>
            <th>Closed</th>
            <th>Side</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>Qty</th>
            <th>PnL</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {trades.slice(0, 50).map((t, i) => (
            <tr key={i}>
              <td className="surface-table__mono">{t.opened_at ? t.opened_at.slice(0, 16).replace("T", " ") : "—"}</td>
              <td className="surface-table__mono">{t.closed_at ? t.closed_at.slice(0, 16).replace("T", " ") : "—"}</td>
              <td>
                <span
                  className={`surface-badge ${t.side === "Buy" || t.side === "LONG" ? "surface-badge--buy" : "surface-badge--sell"}`}
                >
                  {t.side}
                </span>
              </td>
              <td className="surface-table__mono">{fmt(t.entry_price ?? 0)}</td>
              <td className="surface-table__mono">{fmt(t.exit_price ?? 0)}</td>
              <td className="surface-table__mono">{fmt(t.qty ?? 0, 4)}</td>
              <td style={{ color: pnlColor(t.pnl ?? 0), fontVariantNumeric: "tabular-nums" }}>
                {t.pnl >= 0 ? "+" : ""}{fmt(t.pnl ?? 0)}
              </td>
              <td style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>{t.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ResultsPanel({ result }: { result: BacktestRunResult }) {
  const pf = typeof result.profit_factor === "number" ? fmt(result.profit_factor) : String(result.profit_factor);
  return (
    <section className="panel">
      <SectionHeading
        title="Results"
        description={`${result.symbol} · ${result.scope} · ${result.interval}m · ${result.days_back}d · ${result.total_candles} candles`}
      />
      <div className="bt-metrics-grid">
        <MetricCard label="Total PnL" value={(result.total_pnl >= 0 ? "+" : "") + fmt(result.total_pnl)} color={pnlColor(result.total_pnl)} />
        <MetricCard label="Win Rate" value={fmt(result.win_rate ?? 0) + "%"} />
        <MetricCard label="Trades" value={String(result.trades)} />
        <MetricCard label="Wins / Losses" value={`${result.wins} / ${result.losses}`} />
        <MetricCard label="Max Drawdown" value={fmt(result.max_drawdown_pct ?? 0) + "%"} color="#fca5a5" />
        <MetricCard label="Sharpe" value={fmt(result.sharpe_ratio ?? 0)} />
        <MetricCard label="Avg Win" value={(result.avg_win >= 0 ? "+" : "") + fmt(result.avg_win)} color="#86efac" />
        <MetricCard label="Avg Loss" value={fmt(result.avg_loss ?? 0)} color="#fca5a5" />
        <MetricCard label="Profit Factor" value={pf} />
      </div>
      <div style={{ marginTop: 20 }}>
        <SectionHeading title="Trade Log" description="Last 50 trades." />
        <TradesTable trades={result.trades_list ?? []} />
      </div>
    </section>
  );
}

export function BacktestPage() {
  const [scope, setScope] = useState<"futures" | "spot">("futures");
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setInterval] = useState("15");
  const [daysBack, setDaysBack] = useState(30);
  const [balance, setBalance] = useState(10000);
  const [result, setResult] = useState<BacktestRunResult | null>(null);

  const mutation = useMutation({
    mutationFn: runBacktest,
    onSuccess: (data) => setResult(data),
  });

  function handleRun() {
    mutation.mutate({ scope, symbol, interval: interval as "1" | "5" | "15" | "60", days_back: daysBack, balance });
  }

  return (
    <AppShell>
      <div className="app-route backtest-layout">
        <PageIntro
          eyebrow="Strategy"
          title="Backtest"
          description="Simulate the trading strategy on historical OHLCV data. Requires local database with candle data."
          meta={
            <>
              <p className="status-caption">Mode: historical simulation</p>
              <p className="status-caption">Engine: FuturesBacktestRunner / SpotBacktestRunner</p>
            </>
          }
        />

        <section className="panel">
          <SectionHeading title="Parameters" description="Configure and run a backtest simulation." />
          <div className="bt-form">
            <div className="bt-form__row">
              <label className="bt-form__label">Scope</label>
              <div className="bt-form__field">
                {SCOPES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={scope === s ? "button-primary" : "button-secondary"}
                    style={{ padding: "8px 16px", fontSize: "0.88rem" }}
                    onClick={() => setScope(s)}
                  >
                    {s === "futures" ? "Futures" : "Spot"}
                  </button>
                ))}
              </div>
            </div>

            <div className="bt-form__row">
              <label className="bt-form__label" htmlFor="bt-symbol">Symbol</label>
              <select
                id="bt-symbol"
                className="settings-field__input bt-form__select"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              >
                {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            <div className="bt-form__row">
              <label className="bt-form__label">Interval</label>
              <div className="bt-form__field">
                {INTERVALS.map((iv) => (
                  <button
                    key={iv.value}
                    type="button"
                    className={interval === iv.value ? "button-primary" : "button-secondary"}
                    style={{ padding: "8px 14px", fontSize: "0.88rem" }}
                    onClick={() => setInterval(iv.value)}
                  >
                    {iv.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="bt-form__row">
              <label className="bt-form__label" htmlFor="bt-days">Days back</label>
              <input
                id="bt-days"
                type="number"
                className="settings-field__input bt-form__input"
                min={7} max={365}
                value={daysBack}
                onChange={(e) => setDaysBack(Number(e.target.value))}
              />
            </div>

            <div className="bt-form__row">
              <label className="bt-form__label" htmlFor="bt-balance">Initial balance (USDT)</label>
              <input
                id="bt-balance"
                type="number"
                className="settings-field__input bt-form__input"
                min={100}
                value={balance}
                onChange={(e) => setBalance(Number(e.target.value))}
              />
            </div>

            <div className="bt-form__row" style={{ paddingTop: 8 }}>
              <span />
              <button
                type="button"
                className="button-primary"
                disabled={mutation.isPending}
                onClick={handleRun}
                style={{ minWidth: 160 }}
              >
                {mutation.isPending ? "Running…" : "▶ Run Backtest"}
              </button>
            </div>
          </div>
        </section>

        {mutation.isError ? (
          <section className="panel">
            <p className="inline-error">
              {mutation.error instanceof Error ? mutation.error.message : "Backtest request failed."}
            </p>
          </section>
        ) : null}

        {result?.error ? (
          <section className="panel">
            <SectionHeading title="Backtest Error" description="" />
            <p className="inline-error">{result.error}</p>
          </section>
        ) : null}

        {result && !result.error ? <ResultsPanel result={result} /> : null}
      </div>
    </AppShell>
  );
}
