type AnalyticsSummaryCardProps = {
  eyebrow: string;
  label: string;
  value: string | number;
  note: string;
  tone?: "neutral" | "positive" | "negative";
  testId: string;
};

function valueClass(tone: AnalyticsSummaryCardProps["tone"]) {
  if (tone === "positive") {
    return "analytics-summary-card__value futures-pnl futures-pnl--positive";
  }
  if (tone === "negative") {
    return "analytics-summary-card__value futures-pnl futures-pnl--negative";
  }
  return "analytics-summary-card__value";
}

export function AnalyticsSummaryCard({ eyebrow, label, value, note, tone = "neutral", testId }: AnalyticsSummaryCardProps) {
  return (
    <article className="summary-card analytics-summary-card" data-testid={testId}>
      <p className="analytics-summary-card__eyebrow">{eyebrow}</p>
      <p className="analytics-summary-card__label">{label}</p>
      <p className={valueClass(tone)}>{value}</p>
      <p className="analytics-summary-card__note">{note}</p>
    </article>
  );
}
