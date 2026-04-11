type ModelsSummaryCardProps = {
  label: string;
  value: string | number;
  note: string;
  testId: string;
};

export function ModelsSummaryCard({ label, value, note, testId }: ModelsSummaryCardProps) {
  return (
    <section className="panel" data-testid={testId}>
      <p className="spot-summary-card__label">{label}</p>
      <p className="spot-summary-card__value">{value}</p>
      <p className="summary-card__note">{note}</p>
    </section>
  );
}
