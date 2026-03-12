"""
Database operations using SQLite + SQLAlchemy
Các thao tác cơ sở dữ liệu sử dụng SQLite + SQLAlchemy

Tables:
  - candles       : Historical OHLCV data / Dữ liệu OHLCV lịch sử
  - trades        : Trade records / Bản ghi giao dịch
  - performance   : Daily performance snapshots / Ảnh chụp hiệu suất hàng ngày
"""

from __future__ import annotations

import csv
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import create_engine, text
import structlog

logger = structlog.get_logger(__name__)


class Database:
    """
    SQLite database manager for the Forex trading bot.
    Quản lý cơ sở dữ liệu SQLite cho bot giao dịch Forex.
    """

    def __init__(self, db_path: str = "./trading_bot.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

    # ------------------------------------------------------------------ #
    # Schema / Lược đồ                                                     #
    # ------------------------------------------------------------------ #

    def initialize(self) -> None:
        """
        Create all tables if they don't exist.
        Tạo tất cả bảng nếu chưa tồn tại.
        """
        with self.engine.begin() as conn:
            # OHLCV candles / Nến OHLCV
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS candles (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT    NOT NULL,
                    timeframe   TEXT    NOT NULL,
                    timestamp   DATETIME NOT NULL,
                    open        REAL    NOT NULL,
                    high        REAL    NOT NULL,
                    low         REAL    NOT NULL,
                    close       REAL    NOT NULL,
                    volume      REAL    NOT NULL,
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, timeframe, timestamp)
                )
            """))

            # Trade records / Bản ghi giao dịch
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS trades (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket              INTEGER,
                    symbol              TEXT    NOT NULL,
                    timeframe           TEXT    NOT NULL,
                    order_type          TEXT    NOT NULL,
                    entry_price         REAL,
                    sl_price            REAL,
                    tp_price            REAL,
                    lot_size            REAL,
                    pattern             TEXT,
                    pattern_confidence  REAL,
                    decision_reason     TEXT,
                    status              TEXT    DEFAULT 'OPEN',
                    pnl                 REAL    DEFAULT 0,
                    close_price         REAL,
                    open_time           DATETIME DEFAULT CURRENT_TIMESTAMP,
                    close_time          DATETIME,
                    cycle               INTEGER
                )
            """))

            # Daily performance snapshots / Ảnh chụp hiệu suất hàng ngày
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS performance (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    snap_date       DATE    NOT NULL UNIQUE,
                    total_trades    INTEGER DEFAULT 0,
                    winning_trades  INTEGER DEFAULT 0,
                    losing_trades   INTEGER DEFAULT 0,
                    total_pnl       REAL    DEFAULT 0,
                    win_rate        REAL    DEFAULT 0,
                    profit_factor   REAL    DEFAULT 0,
                    max_drawdown    REAL    DEFAULT 0,
                    sharpe_ratio    REAL    DEFAULT 0,
                    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))

        logger.info("Database initialized", path=self.db_path)

    # ------------------------------------------------------------------ #
    # Candles / Nến                                                         #
    # ------------------------------------------------------------------ #

    def save_candles(self, df: pd.DataFrame, symbol: str, timeframe: str) -> int:
        """
        Upsert candles from a DataFrame.
        Upsert nến từ DataFrame.

        Returns number of rows inserted.
        """
        if df.empty:
            return 0

        df = df.copy()
        df["symbol"] = symbol
        df["timeframe"] = timeframe

        # Normalise timestamp column name / Chuẩn hóa tên cột timestamp
        if "time" in df.columns:
            df = df.rename(columns={"time": "timestamp"})
        if "tick_volume" in df.columns and "volume" not in df.columns:
            df = df.rename(columns={"tick_volume": "volume"})

        saved = 0
        with self.engine.begin() as conn:
            for _, row in df.iterrows():
                try:
                    conn.execute(
                        text("""
                            INSERT OR IGNORE INTO candles
                                (symbol, timeframe, timestamp, open, high, low, close, volume)
                            VALUES
                                (:symbol, :timeframe, :timestamp, :open, :high, :low, :close, :volume)
                        """),
                        {
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "timestamp": str(row.get("timestamp", row.name)),
                            "open": float(row["open"]),
                            "high": float(row["high"]),
                            "low": float(row["low"]),
                            "close": float(row["close"]),
                            "volume": float(row.get("volume", 0)),
                        },
                    )
                    saved += 1
                except Exception:
                    pass
        return saved

    def get_candles(
        self, symbol: str, timeframe: str, limit: int = 500
    ) -> pd.DataFrame:
        """
        Retrieve candles ordered oldest-first.
        Truy xuất nến theo thứ tự cũ nhất trước.
        """
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    text("""
                        SELECT timestamp, open, high, low, close, volume
                        FROM   candles
                        WHERE  symbol = :s AND timeframe = :tf
                        ORDER  BY timestamp DESC
                        LIMIT  :lim
                    """),
                    {"s": symbol, "tf": timeframe, "lim": limit},
                ).fetchall()

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
            df["time"] = pd.to_datetime(df["time"])
            return df.sort_values("time").reset_index(drop=True)
        except Exception as e:
            logger.error("get_candles failed", error=str(e))
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    # Trades / Giao dịch                                                   #
    # ------------------------------------------------------------------ #

    def save_trade(self, trade: Dict[str, Any]) -> int:
        """
        Insert a new trade record.
        Chèn bản ghi giao dịch mới.
        """
        try:
            with self.engine.begin() as conn:
                result = conn.execute(
                    text("""
                        INSERT INTO trades
                            (ticket, symbol, timeframe, order_type, entry_price,
                             sl_price, tp_price, lot_size, pattern, pattern_confidence,
                             decision_reason, status, cycle)
                        VALUES
                            (:ticket, :symbol, :timeframe, :order_type, :entry_price,
                             :sl_price, :tp_price, :lot_size, :pattern, :pattern_confidence,
                             :decision_reason, :status, :cycle)
                    """),
                    {
                        "ticket": trade.get("ticket"),
                        "symbol": trade.get("symbol", ""),
                        "timeframe": trade.get("timeframe", ""),
                        "order_type": trade.get("order_type", "HOLD"),
                        "entry_price": trade.get("entry_price"),
                        "sl_price": trade.get("sl_price"),
                        "tp_price": trade.get("tp_price"),
                        "lot_size": trade.get("lot_size"),
                        "pattern": trade.get("pattern", ""),
                        "pattern_confidence": trade.get("pattern_confidence"),
                        "decision_reason": trade.get("decision_reason", ""),
                        "status": trade.get("status", "OPEN"),
                        "cycle": trade.get("cycle"),
                    },
                )
            return result.lastrowid  # type: ignore[return-value]
        except Exception as e:
            logger.error("save_trade failed", error=str(e))
            return -1

    def update_trade(self, trade_id: int, updates: Dict[str, Any]) -> None:
        """Update a trade record (e.g. close it) / Cập nhật bản ghi giao dịch."""
        if not updates:
            return
        cols = ", ".join(f"{k} = :{k}" for k in updates)
        updates["_id"] = trade_id
        with self.engine.begin() as conn:
            conn.execute(text(f"UPDATE trades SET {cols} WHERE id = :_id"), updates)

    def get_trades(
        self, status: Optional[str] = None, limit: int = 500
    ) -> List[Dict[str, Any]]:
        """Fetch trades, optionally filtered by status / Lấy giao dịch, tùy chọn lọc theo trạng thái."""
        try:
            where = "WHERE status = :status" if status else ""
            params: Dict[str, Any] = {"limit": limit}
            if status:
                params["status"] = status
            with self.engine.connect() as conn:
                result = conn.execute(
                    text(f"SELECT * FROM trades {where} ORDER BY open_time DESC LIMIT :limit"),
                    params,
                )
                cols = list(result.keys())
                return [dict(zip(cols, row)) for row in result.fetchall()]
        except Exception as e:
            logger.error("get_trades failed", error=str(e))
            return []

    def export_trades_csv(self, filepath: str = "./reports/trades.csv") -> None:
        """Export all trades to CSV / Xuất tất cả giao dịch sang CSV."""
        trades = self.get_trades(limit=100_000)
        if not trades:
            return
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=trades[0].keys())
            writer.writeheader()
            writer.writerows(trades)
        logger.info("Trades exported to CSV", path=filepath)

    # ------------------------------------------------------------------ #
    # Performance Statistics / Thống kê hiệu suất                          #
    # ------------------------------------------------------------------ #

    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Compute live performance metrics from the trades table.
        Tính toán số liệu hiệu suất trực tiếp từ bảng trades.
        """
        try:
            trades = self.get_trades(limit=100_000)
            if not trades:
                return {"total_trades": 0, "message": "No trades recorded yet."}

            df = pd.DataFrame(trades)
            closed = df[df["status"] == "CLOSED"] if "status" in df.columns else df

            if closed.empty:
                return {
                    "total_trades": len(df),
                    "open_trades": len(df[df["status"] == "OPEN"]) if "status" in df.columns else 0,
                    "message": "No closed trades yet.",
                }

            total = len(closed)
            pnl_col = closed["pnl"].astype(float) if "pnl" in closed.columns else pd.Series([0.0])

            winners = int((pnl_col > 0).sum())
            losers = int((pnl_col < 0).sum())
            total_pnl = float(pnl_col.sum())
            win_rate = round(winners / total * 100, 2) if total else 0.0
            gross_profit = float(pnl_col[pnl_col > 0].sum())
            gross_loss = abs(float(pnl_col[pnl_col < 0].sum()))
            profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

            # Max drawdown (running peak to trough) / Drawdown tối đa
            cumulative = pnl_col.cumsum()
            rolling_max = cumulative.cummax()
            drawdown = (cumulative - rolling_max).min()

            # Sharpe ratio (annualised, assuming 252 trading days)
            # Tỷ lệ Sharpe (được hàng năm hóa, giả sử 252 ngày giao dịch)
            if len(pnl_col) > 1:
                sharpe = round(
                    (pnl_col.mean() / pnl_col.std()) * (252 ** 0.5)
                    if pnl_col.std() != 0
                    else 0.0,
                    2,
                )
            else:
                sharpe = 0.0

            return {
                "total_trades": total,
                "winning_trades": winners,
                "losing_trades": losers,
                "win_rate": win_rate,
                "total_pnl": round(total_pnl, 2),
                "gross_profit": round(gross_profit, 2),
                "gross_loss": round(gross_loss, 2),
                "profit_factor": profit_factor,
                "max_drawdown": round(float(drawdown), 2),
                "sharpe_ratio": sharpe,
            }
        except Exception as e:
            logger.error("get_performance_stats failed", error=str(e))
            return {}

    def close(self) -> None:
        """Close all connections / Đóng tất cả kết nối."""
        self.engine.dispose()
        logger.info("Database connection closed")
