import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import { useOrderbook } from "./hooks/useOrderbook";
import type { OrderbookLevel } from "../../shared/contracts";

const SYMBOLS = [
  { label: "BTCUSDT (linear)", value: "BTCUSDT", category: "linear" },
  { label: "ETHUSDT (linear)", value: "ETHUSDT", category: "linear" },
  { label: "SOLUSDT (linear)", value: "SOLUSDT", category: "linear" },
  { label: "XRPUSDT (linear)", value: "XRPUSDT", category: "linear" },
  { label: "BTCUSDT (spot)", value: "BTCUSDT", category: "spot" },
  { label: "ETHUSDT (spot)", value: "ETHUSDT", category: "spot" },
];

function fmt(value: string, decimals = 2): string {
  const n = parseFloat(value);
  if (Number.isNaN(n)) return value;
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function LevelsTable({
  levels,
  side,
}: {
  levels: OrderbookLevel[];
  side: "bids" | "asks";
}) {
  const isBid = side === "bids";
  return (
    <div className="ob-side">
      <div
        className="ob-side__header"
        style={{
          background: isBid ? "rgba(34,197,94,0.08)" : "rgba(248,113,113,0.08)",
          borderBottom: `1px solid ${isBid ? "rgba(34,197,94,0.18)" : "rgba(248,113,113,0.18)"}`,
        }}
      >
        <span style={{ color: isBid ? "#86efac" : "#fca5a5", fontWeight: 700 }}>
          {isBid ? "▲ BIDS" : "▼ ASKS"}
        </span>
        <span className="ob-side__col">PRICE</span>
        <span className="ob-side__col">SIZE</span>
        <span className="ob-side__col">TOTAL</span>
      </div>
      <div className="ob-side__body">
        {levels.map((level, i) => (
          <div key={i} className="ob-level">
            <span
              style={{
                color: isBid ? "#86efac" : "#fca5a5",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {fmt(level.price, 2)}
            </span>
            <span className="ob-level__num">{fmt(level.size, 4)}</span>
            <span className="ob-level__num" style={{ color: "var(--text-muted)" }}>
              {fmt(level.total, 0)}
            </span>
          </div>
        ))}
        {levels.length === 0 && (
          <p className="panel-muted" style={{ textAlign: "center", padding: "20px 0" }}>
            Нет данных
          </p>
        )}
      </div>
    </div>
  );
}

export function OrderbookPage() {
  const [selected, setSelected] = useState(0);
  const qc = useQueryClient();
  const { value: symbol, category } = SYMBOLS[selected];
  const query = useOrderbook(symbol, category);
  const snap = query.data;

  function handleChange(idx: number) {
    setSelected(idx);
  }

  return (
    <AppShell>
      <div className="app-route orderbook-layout">
        <PageIntro
          eyebrow="Рыночные данные"
          title="Стакан ордеров"
          description="Стакан второго уровня из Bybit REST API. Обновление каждые 20 секунд."
          meta={
            <>
              <p className="status-caption">Символ: {symbol}</p>
              <p className="status-caption">Категория: {category}</p>
              {snap?.generated_at ? (
                <p className="status-caption">
                  Обновлено: {new Date(snap.generated_at).toLocaleTimeString()}
                </p>
              ) : null}
            </>
          }
        />

        <section className="panel">
          <SectionHeading title="Инструмент" description="Выберите рынок для просмотра стакана." />
          <div className="ob-controls">
            <select
              className="settings-field__input"
              style={{ maxWidth: 280 }}
              value={selected}
              onChange={(e) => handleChange(Number(e.target.value))}
            >
              {SYMBOLS.map((s, i) => (
                <option key={i} value={i}>
                  {s.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="button-secondary"
              onClick={() => void qc.invalidateQueries({ queryKey: ["orderbook", symbol, category] })}
            >
              Обновить
            </button>
          </div>
        </section>

        {snap?.error ? (
          <section className="panel">
            <p className="inline-error">{snap.error}</p>
          </section>
        ) : null}

        {query.isError ? (
          <section className="panel">
            <p className="inline-error">Не удалось загрузить стакан ордеров.</p>
          </section>
        ) : null}

        <section className="panel ob-panel" data-testid="orderbook.panel">
          <div className="ob-grid">
            <LevelsTable levels={snap?.bids ?? []} side="bids" />
            <LevelsTable levels={snap?.asks ?? []} side="asks" />
          </div>
        </section>
      </div>
    </AppShell>
  );
}
