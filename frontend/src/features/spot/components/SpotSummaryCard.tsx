interface SpotSummaryCardProps {
  label: string;
  value: string | number;
  note: string;
  testId: string;
  uiScope: string;
}

export function SpotSummaryCard({ label, value, note, testId, uiScope }: SpotSummaryCardProps) {
  return (
    <article
      className="panel spot-summary-card"
      data-testid={testId}
      data-ui-role="summary-card"
      data-ui-scope={uiScope}
    >
      <p className="spot-summary-card__eyebrow">Снепшот</p>
      <p className="spot-summary-card__label">{label}</p>
      <p className="spot-summary-card__value">{value}</p>
      <p className="panel-muted spot-summary-card__note">{note}</p>
    </article>
  );
}
