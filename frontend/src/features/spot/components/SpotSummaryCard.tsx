interface SpotSummaryCardProps {
  label: string;
  value: string | number;
  note: string;
  testId: string;
}

export function SpotSummaryCard({ label, value, note, testId }: SpotSummaryCardProps) {
  return (
    <article className="panel spot-summary-card" data-testid={testId}>
      <p className="spot-summary-card__eyebrow">Snapshot Metric</p>
      <p className="spot-summary-card__label">{label}</p>
      <p className="spot-summary-card__value">{value}</p>
      <p className="panel-muted spot-summary-card__note">{note}</p>
    </article>
  );
}
