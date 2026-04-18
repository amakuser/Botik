import { AppShell } from "../../shared/ui/AppShell";
import { PageIntro } from "../../shared/ui/PageIntro";
import { SectionHeading } from "../../shared/ui/SectionHeading";
import { useMarketTicker } from "./hooks/useMarketTicker";
import type { MarketTickerEntry } from "../../shared/contracts";

function formatPrice(value: string): string {
  const n = parseFloat(value);
  if (Number.isNaN(n)) return value;
  return n >= 1000
    ? n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : n.toPrecision(5);
}

function formatPct(value: string): string {
  const n = parseFloat(value) * 100;
  if (Number.isNaN(n)) return value;
  return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
}

function formatVolume(value: string): string {
  const n = parseFloat(value);
  if (Number.isNaN(n)) return value;
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + "B";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toFixed(0);
}

function TickerCard({ ticker }: { ticker: MarketTickerEntry }) {
  const pct = parseFloat(ticker.price_24h_pcnt) * 100;
  const isUp = pct >= 0;

  return (
    <article
      className="market-card panel"
      style={{
        borderColor: isUp ? "rgba(34,197,94,0.18)" : "rgba(248,113,113,0.18)",
      }}
    >
      <div className="market-card__symbol">{ticker.symbol.replace("USDT", "")}<span className="market-card__quote">USDT</span></div>
      <div className="market-card__price">${formatPrice(ticker.last_price)}</div>
      <div
        className="market-card__change"
        style={{ color: isUp ? "#86efac" : "#fca5a5" }}
      >
        {formatPct(ticker.price_24h_pcnt)}
      </div>
      <div className="market-card__meta">
        <span>Vol: ${formatVolume(ticker.turnover_24h)}</span>
        <span>H: ${formatPrice(ticker.high_price_24h)}</span>
        <span>L: ${formatPrice(ticker.low_price_24h)}</span>
      </div>
    </article>
  );
}

export function MarketPage() {
  const tickerQuery = useMarketTicker();
  const tickers = tickerQuery.data?.tickers ?? [];
  const error = tickerQuery.data?.error;

  return (
    <AppShell>
      <div className="app-route market-layout">
        <PageIntro
          eyebrow="Live Data"
          title="Market"
          description="Real-time prices for top Bybit Linear Perpetuals. Refreshes every 5 seconds."
          meta={
            <>
              <p className="status-caption">
                Source: {tickerQuery.data?.source ?? "loading"}
              </p>
              <p className="status-caption">
                Symbols: {tickers.length}
              </p>
              {tickerQuery.data?.generated_at ? (
                <p className="status-caption">
                  Updated: {new Date(tickerQuery.data.generated_at).toLocaleTimeString()}
                </p>
              ) : null}
            </>
          }
        />

        {error ? (
          <section className="panel">
            <SectionHeading title="Connection Error" description="Could not reach Bybit public API." />
            <p className="inline-error">{error}</p>
          </section>
        ) : null}

        {tickerQuery.isError ? (
          <section className="panel">
            <p className="inline-error">Failed to fetch market data.</p>
          </section>
        ) : null}

        {tickers.length > 0 ? (
          <section className="panel market-panel">
            <SectionHeading
              title="Linear Perpetuals"
              description="Bybit public market data — no authentication required."
            />
            <div className="market-grid">
              {tickers.map((ticker) => (
                <TickerCard key={ticker.symbol} ticker={ticker} />
              ))}
            </div>
          </section>
        ) : !tickerQuery.isError && !error ? (
          <section className="panel">
            <p className="panel-muted">Loading market data…</p>
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}
