import { AnalyticsEquityPoint } from "../../../shared/contracts";

type AnalyticsEquityCurveTableProps = {
  points: AnalyticsEquityPoint[];
};

export function AnalyticsEquityCurveTable({ points }: AnalyticsEquityCurveTableProps) {
  if (points.length === 0) {
    return (
      <div className="surface-table-empty">
        <strong>Точек кривой доходности нет.</strong>
        <p className="panel-muted">Накопленная серия появится после первых закрытых сделок.</p>
      </div>
    );
  }

  return (
    <div className="surface-table-wrap">
      <table className="surface-table" data-testid="analytics.equity.table">
        <thead>
          <tr>
            <th>Дата</th>
            <th>Дневной PnL</th>
            <th>Накопленный PnL</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point, index) => (
            <tr key={`${point.date}-${index}`} data-testid={`analytics.equity.${point.date}`}>
              <td>
                <div className="surface-table__stack">
                  <span className="surface-table__primary">{point.date}</span>
                  <span className="panel-muted">{index === points.length - 1 ? "Последняя точка" : "Историческая точка"}</span>
                </div>
              </td>
              <td>
                <span className={point.daily_pnl < 0 ? "futures-pnl futures-pnl--negative" : "futures-pnl futures-pnl--positive"}>
                  {point.daily_pnl.toFixed(4)}
                </span>
              </td>
              <td>
                <span className={point.cumulative_pnl < 0 ? "futures-pnl futures-pnl--negative" : "futures-pnl futures-pnl--positive"}>
                  {point.cumulative_pnl.toFixed(4)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
