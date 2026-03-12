"""
Technical Indicator Tools using `ta` library
Cong cu chi bao ky thuat dung thu vien `ta`

Computes: SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Stochastic
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
    Tinh toan bo chi bao ky thuat day du va tra ve gia tri moi nhat.
    """

    name: str = "calculate_indicators"
    description: str = (
        "Compute SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Stochastic "
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
            shared_state.latest_indicators[f"{symbol}_{timeframe}"] = result
            return json.dumps(result)
        except Exception as e:
            logger.error("Indicator calculation failed", error=str(e))
            return json.dumps({"error": str(e)})


# ────────────────────────────────────────────────────────────────────────────
# Core computation using `ta` library
# ────────────────────────────────────────────────────────────────────────────

def _compute_indicators(df: pd.DataFrame, symbol: str, timeframe: str) -> Dict[str, Any]:
    import ta
    from ta.trend import SMAIndicator, EMAIndicator, MACD
    from ta.momentum import RSIIndicator, StochasticOscillator
    from ta.volatility import BollingerBands, AverageTrueRange

    close = df["close"]
    high  = df["high"]
    low   = df["low"]
    n     = len(df)

    result: Dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": n,
    }

    # ── Price basics ─────────────────────────────────────────────────────
    result["price_current"] = round(float(close.iloc[-1]), 5)
    result["price_prev"]    = round(float(close.iloc[-2]), 5) if n >= 2 else None
    if n >= 2:
        result["price_change_pct"] = round(
            (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100, 4
        )

    # ── SMA ──────────────────────────────────────────────────────────────
    for period in [20, 50, 200]:
        if n >= period:
            result[f"sma_{period}"] = _last(SMAIndicator(close, window=period).sma_indicator())

    # ── EMA ──────────────────────────────────────────────────────────────
    for period in [9, 21, 55]:
        if n >= period:
            result[f"ema_{period}"] = _last(EMAIndicator(close, window=period).ema_indicator())

    # ── RSI ──────────────────────────────────────────────────────────────
    if n >= 15:
        rsi_val = _last(RSIIndicator(close, window=14).rsi())
        result["rsi_14"] = rsi_val
        result["rsi_signal"] = (
            "overbought" if rsi_val and rsi_val > 70
            else "oversold" if rsi_val and rsi_val < 30
            else "neutral"
        )

    # ── MACD ─────────────────────────────────────────────────────────────
    if n >= 35:
        macd_obj = MACD(close, window_slow=26, window_fast=12, window_sign=9)
        macd_line = _last(macd_obj.macd())
        signal    = _last(macd_obj.macd_signal())
        histogram = _last(macd_obj.macd_diff())
        result["macd_line"]      = macd_line
        result["macd_signal"]    = signal
        result["macd_histogram"] = histogram
        result["macd_trend"]     = "bullish" if histogram and histogram > 0 else "bearish"

    # ── Bollinger Bands ───────────────────────────────────────────────────
    if n >= 20:
        bb = BollingerBands(close, window=20, window_dev=2)
        upper  = _last(bb.bollinger_hband())
        mid    = _last(bb.bollinger_mavg())
        lower  = _last(bb.bollinger_lband())
        result["bb_upper"] = upper
        result["bb_mid"]   = mid
        result["bb_lower"] = lower

        price = result["price_current"]
        if upper and lower and mid:
            if price > upper:
                result["bb_position"] = "above_upper"
            elif price < lower:
                result["bb_position"] = "below_lower"
            elif price > mid:
                result["bb_position"] = "upper_half"
            else:
                result["bb_position"] = "lower_half"

    # ── ATR ───────────────────────────────────────────────────────────────
    if n >= 15:
        result["atr_14"] = _last(AverageTrueRange(high, low, close, window=14).average_true_range())

    # ── Stochastic ────────────────────────────────────────────────────────
    if n >= 20:
        stoch = StochasticOscillator(high, low, close, window=14, smooth_window=3)
        sk = _last(stoch.stoch())
        sd = _last(stoch.stoch_signal())
        result["stoch_k"] = sk
        result["stoch_d"] = sd
        result["stoch_signal"] = (
            "overbought" if sk and sk > 80
            else "oversold" if sk and sk < 20
            else "neutral"
        )

    # ── Overall trend ─────────────────────────────────────────────────────
    result["trend"] = _determine_trend(result)

    return result


def _last(series: pd.Series) -> float | None:
    if series is None or series.empty:
        return None
    val = series.dropna()
    return round(float(val.iloc[-1]), 5) if not val.empty else None


def _determine_trend(ind: Dict[str, Any]) -> str:
    signals = []
    price  = ind.get("price_current", 0)
    ema9   = ind.get("ema_9")
    ema21  = ind.get("ema_21")
    sma50  = ind.get("sma_50")
    sma200 = ind.get("sma_200")

    if ema9 and ema21:
        signals.append("bullish" if ema9 > ema21 else "bearish")
    if price and sma50:
        signals.append("bullish" if price > sma50 else "bearish")
    if price and sma200:
        signals.append("bullish" if price > sma200 else "bearish")

    hist = ind.get("macd_histogram")
    if hist is not None:
        signals.append("bullish" if hist > 0 else "bearish")

    if not signals:
        return "neutral"
    bull = signals.count("bullish")
    bear = signals.count("bearish")
    return "bullish" if bull > bear else "bearish" if bear > bull else "neutral"
