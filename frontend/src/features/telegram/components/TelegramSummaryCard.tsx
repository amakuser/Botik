interface TelegramSummaryCardProps {
  eyebrow: string;
  label: string;
  value: string | number;
  note: string;
  tone?: "neutral" | "positive" | "negative";
  testId: string;
  uiScope: string;
}

function valueClass(tone: TelegramSummaryCardProps["tone"]) {
  if (tone === "positive") {
    return "telegram-summary-card__value futures-pnl futures-pnl--positive";
  }
  if (tone === "negative") {
    return "telegram-summary-card__value futures-pnl futures-pnl--negative";
  }
  return "telegram-summary-card__value";
}

export function TelegramSummaryCard({ eyebrow, label, value, note, tone = "neutral", testId, uiScope }: TelegramSummaryCardProps) {
  return (
    <section className="panel telegram-summary-card" data-ui-role="summary-card" data-ui-scope={uiScope}>
      <p className="telegram-summary-card__eyebrow">{eyebrow}</p>
      <p className="telegram-summary-card__label">{label}</p>
      <p className={valueClass(tone)} data-testid={testId}>
        {value}
      </p>
      <p className="telegram-summary-card__note">{note}</p>
    </section>
  );
}
