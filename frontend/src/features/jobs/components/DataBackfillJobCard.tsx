interface DataBackfillJobCardProps {
  disabled: boolean;
  onStart: () => void;
}

export function DataBackfillJobCard({ disabled, onStart }: DataBackfillJobCardProps) {
  return (
    <section className="panel" aria-labelledby="data-backfill-title">
      <h2 id="data-backfill-title">Data Backfill Job</h2>
      <p className="toolbar-hint">
        Fixed-preset real backfill flow through the existing app-service, Job Manager, worker, and SSE path.
      </p>
      <dl className="job-preset-grid">
        <dt>Symbol</dt>
        <dd data-testid="jobs.backfill.symbol">BTCUSDT</dd>
        <dt>Category</dt>
        <dd data-testid="jobs.backfill.category">spot</dd>
        <dt>Interval</dt>
        <dd data-testid="jobs.backfill.interval">1m</dd>
      </dl>
      <div className="toolbar-actions">
        <button type="button" className="button-primary" onClick={onStart} disabled={disabled}>
          Start Data Backfill
        </button>
      </div>
    </section>
  );
}
