type ModelsSummaryCardProps = {
  eyebrow: string;
  label: string;
  value: string | number;
  note: string;
  testId: string;
};

export function ModelsSummaryCard({ eyebrow, label, value, note, testId }: ModelsSummaryCardProps) {
  return (
    <section className="panel models-summary-card" data-testid={testId}>
      <p className="models-summary-card__eyebrow">{eyebrow}</p>
      <p className="models-summary-card__label">{label}</p>
      <p className="models-summary-card__value">{value}</p>
      <p className="models-summary-card__note">{note}</p>
    </section>
  );
}
