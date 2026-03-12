"""
MetaTrader 5 Tools for CrewAI agents
Công cụ MetaTrader 5 cho các agent CrewAI

Tools:
  - MT5ConnectionTool    : Connect/verify MT5 session
  - MT5FetchDataTool     : Fetch OHLCV candles (real or simulated)
  - MT5AccountInfoTool   : Read balance / equity
  - MT5PlaceOrderTool    : Market order + SL/TP
  - MT5GetPositionsTool  : List open positions
  - MT5ClosePositionTool : Close a specific ticket
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Type

import numpy as np
import pandas as pd
import structlog
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

# MT5 timeframe string → constant mapping
# Ánh xạ chuỗi khung thời gian MT5 → hằng số
_TF_MAP: Dict[str, Any] = {}


def _get_tf_map() -> Dict[str, Any]:
    """Lazy-load MT5 timeframe constants to avoid import errors on non-Windows."""
    global _TF_MAP
    if _TF_MAP:
        return _TF_MAP
    try:
        import MetaTrader5 as mt5

        _TF_MAP = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
        }
    except Exception:
        _TF_MAP = {}
    return _TF_MAP


# ────────────────────────────────────────────────────────────────────────────
# Connection Tool / Công cụ kết nối
# ────────────────────────────────────────────────────────────────────────────

class _ConnInput(BaseModel):
    login: int = Field(description="MT5 account login number")
    password: str = Field(description="MT5 account password")
    server: str = Field(description="Broker server name, e.g. 'ICMarkets-Demo'")


class MT5ConnectionTool(BaseTool):
    """
    Connect to MetaTrader 5.
    Kết nối với MetaTrader 5.
    """

    name: str = "mt5_connect"
    description: str = (
        "Connect to MetaTrader 5 terminal using login credentials. "
        "Call this once before fetching data or placing orders."
    )
    args_schema: Type[BaseModel] = _ConnInput

    def _run(self, login: int, password: str, server: str) -> str:
        try:
            import MetaTrader5 as mt5

            if not mt5.initialize(login=login, password=password, server=server):
                return json.dumps({"success": False, "error": str(mt5.last_error())})

            info = mt5.account_info()
            if info is None:
                return json.dumps({"success": False, "error": "Cannot retrieve account info"})

            return json.dumps({
                "success": True,
                "account": info.login,
                "name": info.name,
                "balance": info.balance,
                "equity": info.equity,
                "currency": info.currency,
                "leverage": info.leverage,
                "server": info.server,
            })
        except ImportError:
            return json.dumps({"success": False, "error": "MetaTrader5 package not installed. Running in simulation mode."})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})


# ────────────────────────────────────────────────────────────────────────────
# Fetch Data Tool / Công cụ lấy dữ liệu
# ────────────────────────────────────────────────────────────────────────────

class _FetchInput(BaseModel):
    symbol: str = Field(description="Currency pair symbol, e.g. 'EURUSD'")
    timeframe: str = Field(description="Timeframe string: M1, M5, M15, M30, H1, H4, D1")
    count: int = Field(default=500, description="Number of candles to fetch (max 5000)")


class MT5FetchDataTool(BaseTool):
    """
    Fetch OHLCV candlestick data from MT5 and store in shared state + SQLite.
    Lấy dữ liệu nến OHLCV từ MT5 và lưu vào trạng thái chia sẻ + SQLite.
    Falls back to simulation data when MT5 is unavailable.
    Dự phòng sang dữ liệu mô phỏng khi MT5 không khả dụng.
    """

    name: str = "mt5_fetch_data"
    description: str = (
        "Fetch OHLCV candlestick data from MetaTrader 5 for a given symbol and timeframe. "
        "Stores data in shared memory and SQLite. Returns a JSON summary."
    )
    args_schema: Type[BaseModel] = _FetchInput

    def _run(self, symbol: str, timeframe: str, count: int = 500) -> str:
        from utils.shared_state import shared_state
        from utils.database import Database

        # Attempt real MT5 fetch
        try:
            import MetaTrader5 as mt5

            tf_map = _get_tf_map()
            tf_const = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_H1)

            if not mt5.initialize():
                raise RuntimeError("MT5 not initialized")

            rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, count)
            if rates is None or len(rates) == 0:
                raise RuntimeError("No rates returned")

            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            if "tick_volume" in df.columns:
                df = df.rename(columns={"tick_volume": "volume"})

            source = "MT5"

        except Exception as e:
            logger.warning("MT5 fetch failed, using simulation", reason=str(e), symbol=symbol)
            df = _simulate_ohlcv(symbol, timeframe, count)
            source = "SIMULATION"

        # Persist / Lưu trữ
        shared_state.set_df(symbol, timeframe, df)

        db = Database()
        db.initialize()
        saved = db.save_candles(df, symbol, timeframe)

        latest = df.iloc[-1]
        return json.dumps({
            "success": True,
            "source": source,
            "symbol": symbol,
            "timeframe": timeframe,
            "candles_fetched": len(df),
            "candles_saved_to_db": saved,
            "latest_time": str(latest["time"]),
            "latest_open": round(float(latest["open"]), 5),
            "latest_high": round(float(latest["high"]), 5),
            "latest_low": round(float(latest["low"]), 5),
            "latest_close": round(float(latest["close"]), 5),
            "latest_volume": round(float(latest["volume"]), 2),
        })


# ────────────────────────────────────────────────────────────────────────────
# Account Info Tool / Công cụ thông tin tài khoản
# ────────────────────────────────────────────────────────────────────────────

class _AccountInput(BaseModel):
    refresh: bool = Field(default=True, description="Set to true to fetch latest account info from MT5")


class MT5AccountInfoTool(BaseTool):
    """
    Get MT5 account balance, equity, margin.
    Lay so du, von chu so huu, ky quy tai khoan MT5.
    """

    name: str = "mt5_account_info"
    description: str = "Retrieve current MetaTrader 5 account info: balance, equity, free margin, profit."
    args_schema: Type[BaseModel] = _AccountInput

    def _run(self, refresh: bool = True) -> str:
        from utils.shared_state import shared_state

        try:
            import MetaTrader5 as mt5

            if not mt5.initialize():
                raise RuntimeError("MT5 not initialized")

            info = mt5.account_info()
            if info is None:
                raise RuntimeError("Cannot get account info")

            shared_state.account_balance = info.balance
            shared_state.account_equity = info.equity

            return json.dumps({
                "login": info.login,
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin,
                "margin_free": info.margin_free,
                "profit": info.profit,
                "currency": info.currency,
                "leverage": info.leverage,
            })
        except Exception as e:
            logger.warning("MT5 account info unavailable, using simulated", reason=str(e))
            return json.dumps({
                "balance": shared_state.account_balance,
                "equity": shared_state.account_equity,
                "margin": 0,
                "margin_free": shared_state.account_balance,
                "profit": 0,
                "currency": "USD",
                "leverage": 100,
                "mode": "SIMULATION",
            })


# ────────────────────────────────────────────────────────────────────────────
# Place Order Tool / Công cụ đặt lệnh
# ────────────────────────────────────────────────────────────────────────────

class _OrderInput(BaseModel):
    symbol: str = Field(description="Currency pair symbol, e.g. 'EURUSD'")
    order_type: str = Field(description="Order direction: 'BUY' or 'SELL'")
    lot_size: float = Field(description="Volume in lots (e.g. 0.01)")
    sl_pips: float = Field(description="Stop-loss distance in pips from entry price")
    tp_pips: float = Field(description="Take-profit distance in pips from entry price")
    comment: str = Field(default="ForexBot", description="Order comment tag")
    magic: int = Field(default=20241201, description="Unique magic number for this bot")


class MT5PlaceOrderTool(BaseTool):
    """
    Place a market order with SL/TP on MT5.
    Đặt lệnh thị trường với SL/TP trên MT5.
    Automatically falls back to simulation if MT5 not connected.
    Tự động dự phòng sang mô phỏng nếu MT5 không kết nối.
    """

    name: str = "mt5_place_order"
    description: str = (
        "Place a BUY or SELL market order on MetaTrader 5 with stop-loss and take-profit. "
        "Returns order ticket and fill details."
    )
    args_schema: Type[BaseModel] = _OrderInput

    def _run(
        self,
        symbol: str,
        order_type: str,
        lot_size: float,
        sl_pips: float,
        tp_pips: float,
        comment: str = "ForexBot",
        magic: int = 20241201,
    ) -> str:
        try:
            import MetaTrader5 as mt5

            if not mt5.initialize():
                raise RuntimeError("MT5 not initialized")

            sym_info = mt5.symbol_info(symbol)
            if sym_info is None:
                raise RuntimeError(f"Symbol {symbol} not found in MT5")

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                raise RuntimeError(f"No tick data for {symbol}")

            point = sym_info.point
            digits = sym_info.digits
            pip = point * 10 if digits in (4, 5) else point

            if order_type.upper() == "BUY":
                price = tick.ask
                mt5_type = mt5.ORDER_TYPE_BUY
                sl = round(price - sl_pips * pip, digits)
                tp = round(price + tp_pips * pip, digits)
            else:
                price = tick.bid
                mt5_type = mt5.ORDER_TYPE_SELL
                sl = round(price + sl_pips * pip, digits)
                tp = round(price - tp_pips * pip, digits)

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(lot_size),
                "type": mt5_type,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": 20,
                "magic": magic,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                retcode = getattr(result, "retcode", -1)
                comment_r = getattr(result, "comment", "no result")
                raise RuntimeError(f"Order failed (retcode={retcode}): {comment_r}")

            return json.dumps({
                "success": True,
                "ticket": result.order,
                "symbol": symbol,
                "type": order_type.upper(),
                "volume": lot_size,
                "price": price,
                "sl": sl,
                "tp": tp,
            })

        except Exception as e:
            logger.warning("MT5 order failed, simulating", reason=str(e))
            sim_ticket = int(np.random.randint(100_000, 999_999))
            return json.dumps({
                "success": True,
                "mode": "SIMULATION",
                "ticket": sim_ticket,
                "symbol": symbol,
                "type": order_type.upper(),
                "volume": lot_size,
                "note": f"Simulated – MT5 unavailable: {str(e)}",
            })


# ────────────────────────────────────────────────────────────────────────────
# Get Positions Tool / Công cụ lấy vị thế
# ────────────────────────────────────────────────────────────────────────────

class _PosInput(BaseModel):
    symbol: Optional[str] = Field(default=None, description="Filter by symbol, or None for all")


class MT5GetPositionsTool(BaseTool):
    """
    List open MT5 positions.
    Liệt kê các vị thế MT5 đang mở.
    """

    name: str = "mt5_get_positions"
    description: str = "Get all currently open positions from MetaTrader 5, optionally filtered by symbol."
    args_schema: Type[BaseModel] = _PosInput

    def _run(self, symbol: Optional[str] = None) -> str:
        try:
            import MetaTrader5 as mt5

            if not mt5.initialize():
                return json.dumps({"positions": [], "mode": "SIMULATION"})

            positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
            if positions is None:
                return json.dumps({"positions": []})

            result = []
            for p in positions:
                result.append({
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                    "volume": p.volume,
                    "open_price": p.price_open,
                    "current_price": p.price_current,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                    "swap": p.swap,
                    "comment": p.comment,
                })

            return json.dumps({"positions": result, "count": len(result)})
        except Exception as e:
            return json.dumps({"positions": [], "error": str(e), "mode": "SIMULATION"})


# ────────────────────────────────────────────────────────────────────────────
# Close Position Tool / Công cụ đóng vị thế
# ────────────────────────────────────────────────────────────────────────────

class _CloseInput(BaseModel):
    ticket: int = Field(description="Order ticket number to close")


class MT5ClosePositionTool(BaseTool):
    """
    Close an open MT5 position by ticket.
    Đóng vị thế MT5 đang mở theo vé lệnh.
    """

    name: str = "mt5_close_position"
    description: str = "Close an open MetaTrader 5 position identified by its ticket number."
    args_schema: Type[BaseModel] = _CloseInput

    def _run(self, ticket: int) -> str:
        try:
            import MetaTrader5 as mt5

            if not mt5.initialize():
                return json.dumps({"success": True, "mode": "SIMULATION", "ticket": ticket})

            position = mt5.positions_get(ticket=ticket)
            if not position:
                return json.dumps({"success": False, "error": f"Ticket {ticket} not found"})

            pos = position[0]
            tick = mt5.symbol_info_tick(pos.symbol)
            close_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": ticket,
                "price": close_price,
                "deviation": 20,
                "magic": pos.magic,
                "comment": "Bot Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return json.dumps({"success": True, "ticket": ticket, "close_price": close_price})

            return json.dumps({"success": False, "error": getattr(result, "comment", "Unknown error")})

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})


# ────────────────────────────────────────────────────────────────────────────
# Simulation helper / Trợ giúp mô phỏng
# ────────────────────────────────────────────────────────────────────────────

_BASE_PRICES = {
    "EURUSD": 1.1000, "GBPUSD": 1.2700, "USDJPY": 150.00,
    "AUDUSD": 0.6500, "USDCAD": 1.3600, "NZDUSD": 0.6000,
    "USDCHF": 0.9050, "EURJPY": 165.00, "GBPJPY": 190.50,
}


def _simulate_ohlcv(symbol: str, timeframe: str, count: int) -> pd.DataFrame:
    """
    Generate realistic-looking random walk OHLCV data.
    Tạo dữ liệu OHLCV đi ngẫu nhiên trông thực tế.
    """
    rng = np.random.default_rng(seed=hash(symbol + timeframe) % (2 ** 32))
    base = _BASE_PRICES.get(symbol, 1.0)
    volatility = base * 0.0005

    freq_map = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min",
                "H1": "1h", "H4": "4h", "D1": "1D", "W1": "1W"}
    freq = freq_map.get(timeframe.upper(), "1h")

    dates = pd.date_range(end=pd.Timestamp.now(), periods=count, freq=freq)
    returns = rng.normal(0, volatility, count)
    close = base + np.cumsum(returns)
    close = np.maximum(close, base * 0.5)

    spread = np.abs(rng.normal(0, volatility * 0.5, count))
    high = close + spread
    low = close - spread
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.integers(1_000, 50_000, count).astype(float)

    return pd.DataFrame({
        "time": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
