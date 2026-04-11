import type { SpotFill } from "../../../shared/contracts";

interface SpotFillsTableProps {
  fills: SpotFill[];
}

function formatQty(value: number) {
  return value.toFixed(8).replace(/0+$/, "").replace(/\.$/, "");
}

function formatPrice(value: number) {
  return value.toFixed(2);
}

export function SpotFillsTable({ fills }: SpotFillsTableProps) {
  if (fills.length === 0) {
    return <p className="panel-muted">No recent spot fills are available in the current read model.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="spot.fills.table">
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
            <tr key={fill.exec_id} data-testid={`spot.fill.${fill.exec_id}`}>
              <td>{fill.symbol}</td>
              <td>{fill.side}</td>
              <td>{formatPrice(fill.price)}</td>
              <td>{formatQty(fill.qty)}</td>
              <td>{fill.fee === null || fill.fee === undefined ? "n/a" : `${fill.fee.toFixed(4)} ${fill.fee_currency ?? ""}`.trim()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
