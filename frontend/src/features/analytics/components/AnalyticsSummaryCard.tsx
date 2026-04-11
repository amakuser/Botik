type AnalyticsSummaryCardProps = {
  label: string;
  value: string | number;
  note: string;
  testId: string;
};

export function AnalyticsSummaryCard({ label, value, note, testId }: AnalyticsSummaryCardProps) {
  return (
    <article className="summary-card" data-testid={testId}>
      <p className="spot-summary-card__label">{label}</p>
      <p className="spot-summary-card__value">{value}</p>
      <p className="summary-card__note">{note}</p>
    </article>
  );
}
