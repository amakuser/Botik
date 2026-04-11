import type { FuturesPosition } from "../../../shared/contracts";

interface FuturesPositionsTableProps {
  positions: FuturesPosition[];
}

function formatNumber(value: number | null | undefined, decimals = 2) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return value.toFixed(decimals);
}

export function FuturesPositionsTable({ positions }: FuturesPositionsTableProps) {
  if (positions.length === 0) {
    return <p className="panel-muted">No open futures positions are available in the current read model.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="futures.positions.table">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th>Qty</th>
            <th>Entry</th>
            <th>Mark</th>
            <th>uPnL</th>
            <th>Protection</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => (
            <tr
              key={`${position.account_type}:${position.symbol}:${position.side}:${position.position_idx}`}
              data-testid={`futures.position.${position.symbol}.${position.side}`}
            >
              <td>{position.symbol}</td>
              <td>{position.side}</td>
              <td>{formatNumber(position.qty, 4)}</td>
              <td>{formatNumber(position.entry_price, 2)}</td>
              <td>{formatNumber(position.mark_price, 2)}</td>
              <td>{formatNumber(position.unrealized_pnl, 4)}</td>
              <td>{position.protection_status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
