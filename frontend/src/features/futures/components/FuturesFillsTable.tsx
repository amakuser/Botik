import type { FuturesFill } from "../../../shared/contracts";

interface FuturesFillsTableProps {
  fills: FuturesFill[];
}

function formatNumber(value: number | null | undefined, decimals = 2) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return value.toFixed(decimals);
}

export function FuturesFillsTable({ fills }: FuturesFillsTableProps) {
  if (fills.length === 0) {
    return <p className="panel-muted">No recent futures fills are available in the current read model.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="futures.fills.table">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th>Price</th>
            <th>Qty</th>
            <th>Fee</th>
          </tr>
        </thead>
        <tbody>
          {fills.map((fill) => (
            <tr key={fill.exec_id} data-testid={`futures.fill.${fill.exec_id}`}>
              <td>{fill.symbol}</td>
              <td>{fill.side}</td>
              <td>{formatNumber(fill.price, 2)}</td>
              <td>{formatNumber(fill.qty, 4)}</td>
              <td>
                {fill.exec_fee === null || fill.exec_fee === undefined
                  ? "n/a"
                  : `${fill.exec_fee.toFixed(4)} ${fill.fee_currency ?? ""}`.trim()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
