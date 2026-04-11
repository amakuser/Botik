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
    return <p className="panel-muted">No active spot holdings are available in the current read model.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="spot.holdings.table">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Total Qty</th>
            <th>Avg Entry</th>
            <th>Hold Reason</th>
            <th>Strategy</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((holding) => (
            <tr key={`${holding.account_type}:${holding.symbol}`} data-testid={`spot.holding.${holding.symbol}`}>
              <td>{holding.symbol}</td>
              <td>{formatQty(holding.total_qty)}</td>
              <td>{formatPrice(holding.avg_entry_price)}</td>
              <td>{holding.hold_reason}</td>
              <td>{holding.strategy_owner ?? "n/a"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
