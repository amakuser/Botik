import sys
from pathlib import Path

from botik_app_service.contracts.backtest import BacktestRunRequest, BacktestRunResult, BacktestTrade


class BacktestRunService:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._botik_src = str(repo_root)

    def run(self, request: BacktestRunRequest) -> BacktestRunResult:
        if self._botik_src not in sys.path:
            sys.path.insert(0, self._botik_src)
        try:
            if request.scope == "futures":
                from src.botik.backtest.backtest_runner import FuturesBacktestRunner  # type: ignore
                runner = FuturesBacktestRunner(
                    symbol=request.symbol,
                    interval=request.interval,
                    days_back=request.days_back,
                    balance=request.balance,
                )
            else:
                from src.botik.backtest.backtest_runner import SpotBacktestRunner  # type: ignore
                runner = SpotBacktestRunner(
                    symbol=request.symbol,
                    interval=request.interval,
                    days_back=request.days_back,
                    balance=request.balance,
                )
            result = runner.run()
            trades = [
                BacktestTrade(
                    opened_at=t.get("opened_at", ""),
                    closed_at=t.get("closed_at", ""),
                    symbol=t.get("symbol", request.symbol),
                    side=t.get("side", ""),
                    entry_price=float(t.get("entry_price", 0)),
                    exit_price=float(t.get("exit_price", 0)),
                    qty=float(t.get("qty", 0)),
                    pnl=float(t.get("pnl", 0)),
                    reason=t.get("reason", ""),
                )
                for t in (result.trades_list or [])
            ]
            pf = result.profit_factor
            return BacktestRunResult(
                scope=request.scope,
                symbol=result.symbol,
                interval=result.interval,
                days_back=request.days_back,
                start_date=result.start_date,
                end_date=result.end_date,
                total_candles=result.total_candles,
                trades=result.trades,
                wins=result.wins,
                losses=result.losses,
                win_rate=result.win_rate,
                total_pnl=result.total_pnl,
                max_drawdown=result.max_drawdown,
                max_drawdown_pct=result.max_drawdown_pct,
                sharpe_ratio=result.sharpe_ratio,
                avg_win=result.avg_win,
                avg_loss=result.avg_loss,
                profit_factor=float(pf) if pf != float("inf") else 9999.0,
                trades_list=trades,
            )
        except ImportError as exc:
            return BacktestRunResult(
                scope=request.scope,
                symbol=request.symbol,
                interval=request.interval,
                days_back=request.days_back,
                error=f"Botik backtest module not available: {exc}",
            )
        except Exception as exc:
            return BacktestRunResult(
                scope=request.scope,
                symbol=request.symbol,
                interval=request.interval,
                days_back=request.days_back,
                error=str(exc),
            )
