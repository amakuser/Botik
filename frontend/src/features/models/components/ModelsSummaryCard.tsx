type ModelsSummaryCardProps = {
  eyebrow: string;
  label: string;
  value: string | number;
  note: string;
  testId: string;
  uiScope: string;
};

export function ModelsSummaryCard({ eyebrow, label, value, note, testId, uiScope }: ModelsSummaryCardProps) {
  return (
    <section
      className="panel models-summary-card"
      data-testid={testId}
      data-ui-role="summary-card"
      data-ui-scope={uiScope}
    >
      <p className="models-summary-card__eyebrow">{eyebrow}</p>
      <p className="models-summary-card__label">{label}</p>
      <p className="models-summary-card__value">{value}</p>
      <p className="models-summary-card__note">{note}</p>
    </section>
  );
}
