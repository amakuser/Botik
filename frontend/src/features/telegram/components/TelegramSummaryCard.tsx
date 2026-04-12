interface TelegramSummaryCardProps {
  eyebrow: string;
  label: string;
  value: string | number;
  note: string;
  tone?: "neutral" | "positive" | "negative";
  testId: string;
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

export function TelegramSummaryCard({ eyebrow, label, value, note, tone = "neutral", testId }: TelegramSummaryCardProps) {
  return (
    <section className="panel telegram-summary-card">
      <p className="telegram-summary-card__eyebrow">{eyebrow}</p>
      <p className="telegram-summary-card__label">{label}</p>
      <p className={valueClass(tone)} data-testid={testId}>
        {value}
      </p>
      <p className="telegram-summary-card__note">{note}</p>
    </section>
  );
}
