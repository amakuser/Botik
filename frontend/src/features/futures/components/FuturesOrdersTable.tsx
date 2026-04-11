import type { FuturesOpenOrder } from "../../../shared/contracts";

interface FuturesOrdersTableProps {
  orders: FuturesOpenOrder[];
}

function formatNumber(value: number | null | undefined, decimals = 2) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return value.toFixed(decimals);
}

export function FuturesOrdersTable({ orders }: FuturesOrdersTableProps) {
  if (orders.length === 0) {
    return <p className="panel-muted">No active futures orders are available in the current read model.</p>;
  }

  return (
    <div className="surface-table-wrap" data-testid="futures.orders.table">
      <table className="surface-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th>Type</th>
            <th>Price</th>
            <th>Qty</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr
              key={order.order_link_id ?? order.order_id ?? `${order.symbol}:${order.updated_at_utc}`}
              data-testid={`futures.order.${order.symbol}`}
            >
              <td>{order.symbol}</td>
              <td>{order.side ?? "n/a"}</td>
              <td>{order.order_type ?? "n/a"}</td>
              <td>{formatNumber(order.price, 2)}</td>
              <td>{formatNumber(order.qty, 4)}</td>
              <td>{order.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
