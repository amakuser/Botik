interface TelegramSummaryCardProps {
  label: string;
  value: string | number;
  note: string;
  testId: string;
}

export function TelegramSummaryCard({ label, value, note, testId }: TelegramSummaryCardProps) {
  return (
    <section className="panel">
      <p className="spot-summary-card__label">{label}</p>
      <p className="spot-summary-card__value" data-testid={testId}>
        {value}
      </p>
      <p className="panel-muted">{note}</p>
    </section>
  );
}
