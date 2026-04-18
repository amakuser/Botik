interface FuturesSummaryCardProps {
  label: string;
  value: string | number;
  note: string;
  testId: string;
}

export function FuturesSummaryCard({ label, value, note, testId }: FuturesSummaryCardProps) {
  return (
    <article className="panel futures-summary-card" data-testid={testId}>
      <p className="futures-summary-card__eyebrow">Риск</p>
      <p className="futures-summary-card__label">{label}</p>
      <p className="futures-summary-card__value">{value}</p>
      <p className="panel-muted futures-summary-card__note">{note}</p>
    </article>
  );
}
