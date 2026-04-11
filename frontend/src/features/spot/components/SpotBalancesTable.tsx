import type { SpotBalance } from "../../../shared/contracts";

interface SpotBalancesTableProps {
  balances: SpotBalance[];
}

function formatQty(value: number) {
  return value.toFixed(8).replace(/0+$/, "").replace(/\.$/, "");
}

export function SpotBalancesTable({ balances }: SpotBalancesTableProps) {
  if (balances.length === 0) {
    return <p className="panel-muted">No spot balances are available in the current read model.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="spot.balances.table">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Asset</th>
            <th>Free</th>
            <th>Locked</th>
            <th>Total</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {balances.map((balance) => (
            <tr key={balance.asset} data-testid={`spot.balance.${balance.asset}`}>
              <td>{balance.asset}</td>
              <td>{formatQty(balance.free_qty)}</td>
              <td>{formatQty(balance.locked_qty)}</td>
              <td>{formatQty(balance.total_qty)}</td>
              <td>{balance.source_of_truth ?? "unknown"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
