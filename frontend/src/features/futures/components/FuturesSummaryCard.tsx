interface FuturesSummaryCardProps {
  label: string;
  value: string | number;
  note: string;
  testId: string;
}

export function FuturesSummaryCard({ label, value, note, testId }: FuturesSummaryCardProps) {
  return (
    <article className="panel spot-summary-card" data-testid={testId}>
      <p className="spot-summary-card__label">{label}</p>
      <p className="spot-summary-card__value">{value}</p>
      <p className="panel-muted">{note}</p>
    </article>
  );
}
