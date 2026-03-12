"""
Technical Indicator Tools using pandas_ta
Công cụ chỉ báo kỹ thuật sử dụng pandas_ta

Computes: SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Stochastic, VWAP
Tính toán: SMA, EMA, RSI, MACD, Dải Bollinger, ATR, Stochastic, VWAP
"""

from __future__ import annotations

import json
from typing import Dict, Any, Type

import numpy as np
import pandas as pd
import structlog
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class _IndicatorInput(BaseModel):
    symbol: str = Field(description="Currency pair symbol, e.g. 'EURUSD'")
    timeframe: str = Field(description="Timeframe string, e.g. 'H1'")


class CalculateIndicatorsTool(BaseTool):
    """
    Calculate a full suite of technical indicators and return latest values.
    Tính toán đầy đủ bộ chỉ báo kỹ thuật và trả về giá trị mới nhất.
    """

    name: str = "calculate_indicators"
    description: str = (
        "Compute SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Stochastic and VWAP "
        "for the latest OHLCV data of a symbol/timeframe pair. "
        "Returns a JSON dict with the most recent values."
    )
    args_schema: Type[BaseModel] = _IndicatorInput

    def _run(self, symbol: str, timeframe: str) -> str:
        from utils.shared_state import shared_state

        df = shared_state.get_df(symbol, timeframe)
        if df is None or df.empty:
            return json.dumps({"error": "No OHLCV data in shared state. Run mt5_fetch_data first."})

        try:
            result = _compute_indicators(df.copy(), symbol, timeframe)

            # Store in shared state for other agents / Lưu vào shared state cho các agent khác
            shared_state.latest_indicators[f"{symbol}_{timeframe}"] = result

            return json.dumps(result)
        except Exception as e:
            logger.error("Indicator calculation failed", error=str(e))
            return json.dumps({"error": str(e)})


# ────────────────────────────────────────────────────────────────────────────
# Core computation
# ────────────────────────────────────────────────────────────────────────────

def _compute_indicators(df: pd.DataFrame, symbol: str, timeframe: str) -> Dict[str, Any]:
    """
    Apply pandas_ta indicators and return the last-row values as a flat dict.
    Áp dụng chỉ báo pandas_ta và trả về giá trị hàng cuối dưới dạng dict phẳng.
    """
    import pandas_ta as ta

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    result: Dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": len(df),
    }

    # ── Price basics ──────────────────────────────────────────────────────
    result["price_current"] = round(float(close.iloc[-1]), 5)
    result["price_prev"] = round(float(close.iloc[-2]), 5)
    result["price_change_pct"] = round(
        (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100, 4
    )

    # ── SMA ───────────────────────────────────────────────────────────────
    for period in [20, 50, 200]:
        if len(df) >= period:
            val = ta.sma(close, length=period)
            result[f"sma_{period}"] = _last(val)

    # ── EMA ───────────────────────────────────────────────────────────────
    for period in [9, 21, 55]:
        if len(df) >= period:
            val = ta.ema(close, length=period)
            result[f"ema_{period}"] = _last(val)

    # ── RSI ───────────────────────────────────────────────────────────────
    if len(df) >= 15:
        rsi = ta.rsi(close, length=14)
        result["rsi_14"] = _last(rsi)
        result["rsi_signal"] = (
            "overbought" if result.get("rsi_14", 50) > 70
            else "oversold" if result.get("rsi_14", 50) < 30
            else "neutral"
        )

    # ── MACD ──────────────────────────────────────────────────────────────
    if len(df) >= 35:
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            result["macd_line"] = _last(macd_df.iloc[:, 0])
            result["macd_signal"] = _last(macd_df.iloc[:, 2])
            result["macd_histogram"] = _last(macd_df.iloc[:, 1])
            hist = result.get("macd_histogram", 0)
            result["macd_trend"] = "bullish" if hist and hist > 0 else "bearish"

    # ── Bollinger Bands ───────────────────────────────────────────────────
    if len(df) >= 20:
        bb = ta.bbands(close, length=20, std=2)
        if bb is not None and not bb.empty:
            result["bb_upper"] = _last(bb.iloc[:, 0])
            result["bb_mid"] = _last(bb.iloc[:, 1])
            result["bb_lower"] = _last(bb.iloc[:, 2])
            result["bb_bandwidth"] = _last(bb.iloc[:, 3])
            result["bb_pct_b"] = _last(bb.iloc[:, 4])

            # Position relative to bands / Vị trí so với dải
            price = result["price_current"]
            upper = result.get("bb_upper", price + 1)
            lower = result.get("bb_lower", price - 1)
            mid = result.get("bb_mid", price)
            if price > upper:
                result["bb_position"] = "above_upper"
            elif price < lower:
                result["bb_position"] = "below_lower"
            elif price > mid:
                result["bb_position"] = "upper_half"
            else:
                result["bb_position"] = "lower_half"

    # ── ATR ───────────────────────────────────────────────────────────────
    if len(df) >= 15:
        atr = ta.atr(high, low, close, length=14)
        result["atr_14"] = _last(atr)

    # ── Stochastic ────────────────────────────────────────────────────────
    if len(df) >= 20:
        stoch = ta.stoch(high, low, close, k=14, d=3, smooth_k=3)
        if stoch is not None and not stoch.empty:
            result["stoch_k"] = _last(stoch.iloc[:, 0])
            result["stoch_d"] = _last(stoch.iloc[:, 1])
            sk = result.get("stoch_k", 50)
            result["stoch_signal"] = (
                "overbought" if sk and sk > 80
                else "oversold" if sk and sk < 20
                else "neutral"
            )

    # ── Trend context ─────────────────────────────────────────────────────
    result["trend"] = _determine_trend(result)

    return result


def _last(series: pd.Series) -> float | None:
    """Return last non-NaN value, rounded to 5 dp."""
    if series is None or series.empty:
        return None
    val = series.dropna()
    return round(float(val.iloc[-1]), 5) if not val.empty else None


def _determine_trend(ind: Dict[str, Any]) -> str:
    """
    Simple multi-indicator trend determination.
    Xác định xu hướng đơn giản sử dụng nhiều chỉ báo.
    """
    signals = []

    price = ind.get("price_current", 0)

    # EMA alignment / Sắp xếp EMA
    ema9 = ind.get("ema_9")
    ema21 = ind.get("ema_21")
    sma50 = ind.get("sma_50")
    sma200 = ind.get("sma_200")

    if ema9 and ema21:
        signals.append("bullish" if ema9 > ema21 else "bearish")
    if price and sma50:
        signals.append("bullish" if price > sma50 else "bearish")
    if price and sma200:
        signals.append("bullish" if price > sma200 else "bearish")

    # MACD direction / Hướng MACD
    macd_hist = ind.get("macd_histogram")
    if macd_hist is not None:
        signals.append("bullish" if macd_hist > 0 else "bearish")

    if not signals:
        return "neutral"

    bull_count = signals.count("bullish")
    bear_count = signals.count("bearish")

    if bull_count > bear_count:
        return "bullish"
    elif bear_count > bull_count:
        return "bearish"
    return "neutral"
