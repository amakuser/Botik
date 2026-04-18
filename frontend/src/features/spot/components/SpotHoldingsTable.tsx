import type { SpotHolding } from "../../../shared/contracts";

interface SpotHoldingsTableProps {
  holdings: SpotHolding[];
}

function formatQty(value: number) {
  return value.toFixed(8).replace(/0+$/, "").replace(/\.$/, "");
}

function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return value.toFixed(2);
}

export function SpotHoldingsTable({ holdings }: SpotHoldingsTableProps) {
  if (holdings.length === 0) {
    return <p className="panel-muted surface-table-empty">Активных холдингов нет.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="spot.holdings.table">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Символ</th>
            <th>Кол-во</th>
            <th>Средняя цена</th>
            <th>Причина удержания</th>
            <th>Стратегия</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((holding) => (
            <tr key={`${holding.account_type}:${holding.symbol}`} data-testid={`spot.holding.${holding.symbol}`}>
              <td className="surface-table__primary">{holding.symbol}</td>
              <td>{formatQty(holding.total_qty)}</td>
              <td>{formatPrice(holding.avg_entry_price)}</td>
              <td>
                <span className="surface-badge">{holding.hold_reason}</span>
              </td>
              <td>{holding.strategy_owner ? <span className="surface-badge surface-badge--soft">{holding.strategy_owner}</span> : "n/a"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
