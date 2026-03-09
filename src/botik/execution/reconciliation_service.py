"""
Exchange reconciliation service for spot holdings and futures positions.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any, Callable

from src.botik.storage.core_store import (
    finish_reconciliation_run,
    insert_account_snapshot,
    insert_event_audit,
    insert_reconciliation_issue,
    start_reconciliation_run,
)
from src.botik.storage.futures_store import (
    insert_futures_fill,
    list_futures_positions,
    upsert_futures_open_order,
    upsert_futures_position,
    upsert_futures_protection,
)
from src.botik.storage.spot_store import (
    insert_spot_fill,
    list_spot_holdings,
    upsert_spot_balance,
    upsert_spot_holding,
    upsert_spot_order,
)


logger = logging.getLogger("botik.reconciliation")


class ExchangeReconciliationService:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        executor: Any,
        market_category: str,
        account_type: str = "UNIFIED",
        managed_symbols: list[str] | Callable[[], list[str]] | None = None,
        symbols_limit: int = 120,
        service_name: str = "runtime",
    ) -> None:
        self.conn = conn
        self.executor = executor
        self.market_category = str(market_category or "spot").strip().lower()
        self.account_type = str(account_type or "UNIFIED").strip().upper()
        self.managed_symbols = managed_symbols
        self.symbols_limit = max(int(symbols_limit), 1)
        self.service_name = str(service_name)

    @staticmethod
    def _f(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _i(value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _symbols(self) -> list[str]:
        raw = self.managed_symbols() if callable(self.managed_symbols) else (self.managed_symbols or [])
        out: list[str] = []
        for symbol in raw:
            s = str(symbol or "").upper().strip()
            if s and s not in out:
                out.append(s)
        return out[: self.symbols_limit]

    def _issue_once(
        self,
        *,
        run_id: str,
        issue_type: str,
        domain: str,
        severity: str,
        details: dict[str, Any],
        symbol: str | None = None,
    ) -> str:
        row = self.conn.execute(
            """
            SELECT issue_id
            FROM reconciliation_issues
            WHERE status='open'
              AND issue_type=?
              AND domain=?
              AND COALESCE(symbol, '') = COALESCE(?, '')
            ORDER BY created_at_utc DESC
            LIMIT 1
            """,
            (issue_type, domain, symbol),
        ).fetchone()
        if row and row[0]:
            return str(row[0])
        return insert_reconciliation_issue(
            self.conn,
            issue_type=issue_type,
            domain=domain,
            severity=severity,
            details=details,
            symbol=symbol,
            reconciliation_run_id=run_id,
            status="open",
        )

    async def run(self, *, trigger_source: str) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "trigger_source": str(trigger_source),
            "category": self.market_category,
            "status": "success",
            "spot_balances_seen": 0,
            "spot_holdings_recovered": 0,
            "orders_seen": 0,
            "orders_orphaned": 0,
            "futures_positions_seen": 0,
            "futures_positions_orphaned": 0,
            "fills_seen": 0,
            "issues_created": 0,
        }
        run_id = start_reconciliation_run(self.conn, trigger_source=trigger_source)
        insert_event_audit(
            self.conn,
            event_type="reconciliation_start",
            domain="shared",
            ref_id=run_id,
            payload={"trigger_source": trigger_source, "category": self.market_category},
        )
        try:
            await self._reconcile_wallet(run_id, summary)
            await self._reconcile_open_orders(run_id, summary)
            await self._reconcile_fills(run_id, summary)
            if self.market_category == "linear":
                await self._reconcile_futures_positions(run_id, summary)
            finish_reconciliation_run(self.conn, reconciliation_run_id=run_id, status="success", summary=summary)
            insert_event_audit(
                self.conn,
                event_type="reconciliation_end",
                domain="shared",
                ref_id=run_id,
                payload=summary,
            )
            return summary
        except Exception as exc:
            summary["status"] = "failed"
            summary["error"] = str(exc)
            finish_reconciliation_run(self.conn, reconciliation_run_id=run_id, status="failed", summary=summary)
            insert_event_audit(
                self.conn,
                event_type="reconciliation_failed",
                domain="shared",
                ref_id=run_id,
                payload=summary,
            )
            logger.exception("Reconciliation failed: %s", exc)
            return summary

    async def _reconcile_wallet(self, run_id: str, summary: dict[str, Any]) -> None:
        resp = await self.executor.get_wallet_balance(account_type=self.account_type)
        if resp.get("retCode") != 0:
            issue_id = self._issue_once(
                run_id=run_id,
                issue_type="wallet_balance_api_error",
                domain="shared",
                severity="error",
                details={"retCode": resp.get("retCode"), "retMsg": resp.get("retMsg")},
            )
            summary["issues_created"] += 1
            insert_event_audit(
                self.conn,
                event_type="reconciliation_issue",
                domain="shared",
                ref_id=issue_id,
                payload={"issue_type": "wallet_balance_api_error"},
            )
            return

        wallets = (resp.get("result") or {}).get("list") or []
        insert_account_snapshot(
            self.conn,
            account_type=self.account_type,
            snapshot_kind="wallet_balance",
            payload={"result": wallets},
            reconciliation_run_id=run_id,
        )
        local_holdings = list_spot_holdings(self.conn, account_type=self.account_type)
        local_by_asset = {str(row.get("base_asset") or "").upper(): row for row in local_holdings}
        seen_assets: set[str] = set()

        for account in wallets:
            for coin_info in (account.get("coin") or []):
                coin = str(coin_info.get("coin") or "").upper().strip()
                if not coin:
                    continue
                total = self._f(coin_info.get("walletBalance") or coin_info.get("equity") or 0.0)
                if total <= 0:
                    continue
                free = self._f(coin_info.get("free") or coin_info.get("availableToWithdraw") or total)
                free = min(max(free, 0.0), total)
                locked = max(total - free, 0.0)
                seen_assets.add(coin)
                upsert_spot_balance(
                    self.conn,
                    account_type=self.account_type,
                    asset=coin,
                    free_qty=free,
                    locked_qty=locked,
                    source_of_truth="exchange_wallet_balance",
                )
                summary["spot_balances_seen"] += 1

                if coin in {"USDT", "USDC", "BUSD"}:
                    continue
                symbol = f"{coin}USDT"
                existing = local_by_asset.get(coin)
                if existing is None:
                    upsert_spot_holding(
                        self.conn,
                        account_type=self.account_type,
                        symbol=symbol,
                        base_asset=coin,
                        free_qty=free,
                        locked_qty=locked,
                        avg_entry_price=None,
                        hold_reason="unknown_recovered_from_exchange",
                        source_of_truth="exchange_wallet_balance",
                        recovered_from_exchange=True,
                        strategy_owner=None,
                        auto_sell_allowed=False,
                    )
                    issue_id = self._issue_once(
                        run_id=run_id,
                        issue_type="spot_asset_recovered_from_exchange",
                        domain="spot",
                        severity="warning",
                        symbol=symbol,
                        details={"asset": coin, "free_qty": free, "locked_qty": locked, "auto_sell_allowed": False},
                    )
                    summary["issues_created"] += 1
                    summary["spot_holdings_recovered"] += 1
                    insert_event_audit(
                        self.conn,
                        event_type="imported_recovered_holding",
                        domain="spot",
                        symbol=symbol,
                        ref_id=issue_id,
                        payload={"asset": coin, "qty": total},
                    )

        for row in local_holdings:
            asset = str(row.get("base_asset") or "").upper()
            qty = self._f(row.get("free_qty")) + self._f(row.get("locked_qty"))
            if not asset or qty <= 0 or asset in seen_assets:
                continue
            symbol = str(row.get("symbol") or f"{asset}USDT")
            upsert_spot_holding(
                self.conn,
                account_type=self.account_type,
                symbol=symbol,
                base_asset=asset,
                free_qty=self._f(row.get("free_qty")),
                locked_qty=self._f(row.get("locked_qty")),
                avg_entry_price=row.get("avg_entry_price"),
                hold_reason="stale_hold",
                source_of_truth="reconciliation_local_db",
                recovered_from_exchange=bool(row.get("recovered_from_exchange")),
                strategy_owner=(str(row.get("strategy_owner")) if row.get("strategy_owner") else None),
                auto_sell_allowed=bool(row.get("auto_sell_allowed")),
            )
            issue_id = self._issue_once(
                run_id=run_id,
                issue_type="local_holding_missing_on_exchange",
                domain="spot",
                severity="warning",
                symbol=symbol,
                details={"asset": asset, "qty": qty},
            )
            summary["issues_created"] += 1
            insert_event_audit(
                self.conn,
                event_type="reconciliation_repair_applied",
                domain="spot",
                symbol=symbol,
                ref_id=issue_id,
                payload={"issue_type": "local_holding_missing_on_exchange", "repair": "mark_stale_hold"},
            )

    async def _reconcile_open_orders(self, run_id: str, summary: dict[str, Any]) -> None:
        resp = await self.executor.get_open_orders()
        if resp.get("retCode") != 0:
            return
        open_list = (resp.get("result") or {}).get("list") or []
        insert_account_snapshot(
            self.conn,
            account_type=self.account_type,
            snapshot_kind=f"{self.market_category}_open_orders",
            payload={"result": open_list},
            reconciliation_run_id=run_id,
        )
        domain = "futures" if self.market_category == "linear" else "spot"
        domain_table = "futures_open_orders" if self.market_category == "linear" else "spot_orders"
        seen_links: set[str] = set()
        seen_ids: set[str] = set()
        for order in open_list:
            symbol = str(order.get("symbol") or "").upper().strip()
            if not symbol:
                continue
            link_id = str(order.get("orderLinkId") or "").strip()
            order_id = str(order.get("orderId") or "").strip()
            summary["orders_seen"] += 1
            if link_id:
                seen_links.add(link_id)
            if order_id:
                seen_ids.add(order_id)

            legacy_row = self.conn.execute(
                """
                SELECT 1 FROM orders
                WHERE (? <> '' AND order_link_id=?)
                   OR (? <> '' AND exchange_order_id=?)
                LIMIT 1
                """,
                (link_id, link_id, order_id, order_id),
            ).fetchone()
            domain_row = self.conn.execute(
                f"""
                SELECT 1 FROM {domain_table}
                WHERE (? <> '' AND order_link_id=?)
                   OR (? <> '' AND order_id=?)
                LIMIT 1
                """,
                (link_id, link_id, order_id, order_id),
            ).fetchone()
            if not legacy_row and not domain_row:
                issue_id = self._issue_once(
                    run_id=run_id,
                    issue_type="orphaned_exchange_order",
                    domain=domain,
                    severity="warning",
                    symbol=symbol,
                    details={"order_id": order_id, "order_link_id": link_id},
                )
                summary["issues_created"] += 1
                summary["orders_orphaned"] += 1
                insert_event_audit(
                    self.conn,
                    event_type="imported_orphaned_order",
                    domain=domain,
                    symbol=symbol,
                    ref_id=issue_id,
                    payload={"order_id": order_id, "order_link_id": link_id},
                )

            if self.market_category == "linear":
                upsert_futures_open_order(
                    self.conn,
                    account_type=self.account_type,
                    symbol=symbol,
                    side=order.get("side"),
                    status=str(order.get("orderStatus") or "New"),
                    order_link_id=(link_id or None),
                    order_id=(order_id or None),
                    order_type=order.get("orderType"),
                    time_in_force=order.get("timeInForce"),
                    price=self._f(order.get("price")),
                    qty=self._f(order.get("qty")),
                    reduce_only=bool(order.get("reduceOnly")),
                    close_on_trigger=bool(order.get("closeOnTrigger")),
                    strategy_owner=self.service_name,
                )
            else:
                upsert_spot_order(
                    self.conn,
                    account_type=self.account_type,
                    symbol=symbol,
                    side=str(order.get("side") or ""),
                    status=str(order.get("orderStatus") or "New"),
                    order_link_id=(link_id or None),
                    order_id=(order_id or None),
                    order_type=order.get("orderType"),
                    time_in_force=order.get("timeInForce"),
                    price=self._f(order.get("price")),
                    qty=self._f(order.get("qty")),
                    filled_qty=self._f(order.get("cumExecQty")),
                    strategy_owner=self.service_name,
                )

        rows = self.conn.execute(
            f"""
            SELECT order_link_id, order_id, symbol
            FROM {domain_table}
            WHERE LOWER(status) IN ('new', 'partiallyfilled', 'partially_filled')
            """
        ).fetchall()
        for link_id, order_id, symbol in rows:
            exists = (str(link_id or "") in seen_links) or (str(order_id or "") in seen_ids)
            if exists:
                continue
            self.conn.execute(f"UPDATE {domain_table} SET status='MissingOnExchange' WHERE order_link_id=?", (link_id,))
            self.conn.commit()
            issue_id = self._issue_once(
                run_id=run_id,
                issue_type="local_order_missing_on_exchange",
                domain=domain,
                severity="warning",
                symbol=str(symbol or ""),
                details={"order_id": order_id, "order_link_id": link_id},
            )
            summary["issues_created"] += 1
            insert_event_audit(
                self.conn,
                event_type="reconciliation_repair_applied",
                domain=domain,
                symbol=str(symbol or ""),
                ref_id=issue_id,
                payload={"issue_type": "local_order_missing_on_exchange", "repair": "mark_missing_on_exchange"},
            )

    async def _reconcile_fills(self, run_id: str, summary: dict[str, Any]) -> None:
        symbols = self._symbols()
        for symbol in symbols:
            resp = await self.executor.get_execution_list(symbol=symbol, limit=100)
            if resp.get("retCode") != 0:
                continue
            items = (resp.get("result") or {}).get("list") or []
            if items:
                insert_account_snapshot(
                    self.conn,
                    account_type=self.account_type,
                    snapshot_kind=f"{self.market_category}_executions",
                    payload={"symbol": symbol, "count": len(items)},
                    reconciliation_run_id=run_id,
                )
            for item in items:
                exec_id = str(item.get("execId") or "").strip()
                if not exec_id:
                    continue
                if self.market_category == "linear":
                    insert_futures_fill(
                        self.conn,
                        account_type=self.account_type,
                        symbol=str(item.get("symbol") or symbol).upper(),
                        side=str(item.get("side") or ""),
                        exec_id=exec_id,
                        order_id=str(item.get("orderId") or "") or None,
                        order_link_id=str(item.get("orderLinkId") or "") or None,
                        price=self._f(item.get("execPrice") or item.get("price")),
                        qty=self._f(item.get("execQty") or item.get("qty")),
                        exec_fee=self._f(item.get("execFee")),
                        fee_currency=str(item.get("feeCurrency") or "") or None,
                        is_maker=bool(item.get("isMaker")),
                        exec_time_ms=self._i(item.get("execTime")),
                    )
                else:
                    insert_spot_fill(
                        self.conn,
                        account_type=self.account_type,
                        symbol=str(item.get("symbol") or symbol).upper(),
                        side=str(item.get("side") or ""),
                        exec_id=exec_id,
                        order_id=str(item.get("orderId") or "") or None,
                        order_link_id=str(item.get("orderLinkId") or "") or None,
                        price=self._f(item.get("execPrice") or item.get("price")),
                        qty=self._f(item.get("execQty") or item.get("qty")),
                        fee=self._f(item.get("execFee")),
                        fee_currency=str(item.get("feeCurrency") or "") or None,
                        is_maker=bool(item.get("isMaker")),
                        exec_time_ms=self._i(item.get("execTime")),
                    )
                summary["fills_seen"] += 1

    async def _reconcile_futures_positions(self, run_id: str, summary: dict[str, Any]) -> None:
        resp = await self.executor.get_positions()
        if resp.get("retCode") != 0:
            return
        pos_list = (resp.get("result") or {}).get("list") or []
        insert_account_snapshot(
            self.conn,
            account_type=self.account_type,
            snapshot_kind="futures_positions",
            payload={"result": pos_list},
            reconciliation_run_id=run_id,
        )
        local_map = {
            (str(row.get("symbol") or "").upper(), str(row.get("side") or ""), int(row.get("position_idx") or 0)): row
            for row in list_futures_positions(self.conn, account_type=self.account_type)
            if abs(self._f(row.get("qty"))) > 0
        }
        exchange_keys: set[tuple[str, str, int]] = set()
        for item in pos_list:
            symbol = str(item.get("symbol") or "").upper().strip()
            side = str(item.get("side") or "").strip()
            qty = self._f(item.get("size") or item.get("qty"))
            if not symbol or not side or abs(qty) <= 0:
                continue
            idx = self._i(item.get("positionIdx"))
            key = (symbol, side, idx)
            exchange_keys.add(key)
            summary["futures_positions_seen"] += 1
            stop_loss = self._f(item.get("stopLoss"))
            take_profit = self._f(item.get("takeProfit"))
            trailing = self._f(item.get("trailingStop"))
            status = "protected" if stop_loss > 0 and take_profit > 0 else "unprotected"
            orphaned = key not in local_map

            upsert_futures_position(
                self.conn,
                account_type=self.account_type,
                symbol=symbol,
                side=side,
                position_idx=idx,
                margin_mode=str(item.get("tradeMode") or item.get("marginMode") or ""),
                leverage=self._f(item.get("leverage")),
                qty=qty,
                entry_price=self._f(item.get("avgPrice") or item.get("entryPrice")),
                mark_price=self._f(item.get("markPrice")),
                liq_price=self._f(item.get("liqPrice")),
                unrealized_pnl=self._f(item.get("unrealisedPnl") or item.get("unrealizedPnl")),
                realized_pnl=self._f(item.get("cumRealisedPnl") or item.get("realizedPnl")),
                take_profit=(take_profit if take_profit > 0 else None),
                stop_loss=(stop_loss if stop_loss > 0 else None),
                trailing_stop=(trailing if trailing > 0 else None),
                protection_status=status,
                strategy_owner=self.service_name,
                source_of_truth="exchange_position_list",
                recovered_from_exchange=orphaned,
            )
            upsert_futures_protection(
                self.conn,
                account_type=self.account_type,
                symbol=symbol,
                side=side,
                position_idx=idx,
                status=status,
                source_of_truth="exchange_position_list",
                stop_loss=(stop_loss if stop_loss > 0 else None),
                take_profit=(take_profit if take_profit > 0 else None),
                trailing_stop=(trailing if trailing > 0 else None),
                details={"size": qty},
            )

            if orphaned:
                issue_id = self._issue_once(
                    run_id=run_id,
                    issue_type="orphaned_exchange_position",
                    domain="futures",
                    severity="error",
                    symbol=symbol,
                    details={"side": side, "position_idx": idx, "qty": qty},
                )
                summary["issues_created"] += 1
                summary["futures_positions_orphaned"] += 1
                insert_event_audit(
                    self.conn,
                    event_type="imported_orphaned_position",
                    domain="futures",
                    symbol=symbol,
                    ref_id=issue_id,
                    payload={"side": side, "position_idx": idx, "qty": qty},
                )
            if status == "unprotected":
                issue_id = self._issue_once(
                    run_id=run_id,
                    issue_type="unprotected_position",
                    domain="futures",
                    severity="critical",
                    symbol=symbol,
                    details={"side": side, "position_idx": idx, "qty": qty},
                )
                summary["issues_created"] += 1
                insert_event_audit(
                    self.conn,
                    event_type="protection_failure",
                    domain="futures",
                    symbol=symbol,
                    ref_id=issue_id,
                    payload={"reason": "missing_stop_take"},
                )

        for key, row in local_map.items():
            if key in exchange_keys:
                continue
            symbol, side, idx = key
            issue_id = self._issue_once(
                run_id=run_id,
                issue_type="local_position_missing_on_exchange",
                domain="futures",
                severity="warning",
                symbol=symbol,
                details={"side": side, "position_idx": idx, "local_qty": self._f(row.get("qty"))},
            )
            summary["issues_created"] += 1
            insert_event_audit(
                self.conn,
                event_type="reconciliation_issue",
                domain="futures",
                symbol=symbol,
                ref_id=issue_id,
                payload={"issue_type": "local_position_missing_on_exchange"},
            )
