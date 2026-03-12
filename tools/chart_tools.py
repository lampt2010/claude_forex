"""
Chart Generation Tools
Công cụ tạo biểu đồ

Generates candlestick charts using mplfinance (static PNG) and Plotly (HTML).
Tạo biểu đồ nến bằng mplfinance (PNG tĩnh) và Plotly (HTML).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Type

import pandas as pd
import structlog
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# mplfinance candlestick chart (PNG)
# ────────────────────────────────────────────────────────────────────────────

class _ChartInput(BaseModel):
    symbol: str = Field(description="Currency pair symbol, e.g. 'EURUSD'")
    timeframe: str = Field(description="Timeframe string, e.g. 'H1'")
    candles: int = Field(default=100, description="Number of most-recent candles to plot")
    output_dir: str = Field(default="./charts", description="Directory to save chart PNG")


class GenerateCandlestickChartTool(BaseTool):
    """
    Generate a candlestick PNG chart with SMA/EMA/Bollinger overlays.
    Tạo biểu đồ nến PNG với lớp phủ SMA/EMA/Bollinger.
    """

    name: str = "generate_candlestick_chart"
    description: str = (
        "Generate a candlestick chart PNG from the latest OHLCV data for a given symbol "
        "and timeframe. Adds SMA20, SMA50, EMA9 and volume subplots. Returns the saved file path."
    )
    args_schema: Type[BaseModel] = _ChartInput

    def _run(
        self,
        symbol: str,
        timeframe: str,
        candles: int = 100,
        output_dir: str = "./charts",
    ) -> str:
        from utils.shared_state import shared_state

        try:
            import mplfinance as mpf
            import matplotlib
            matplotlib.use("Agg")  # headless backend

            df = shared_state.get_df(symbol, timeframe)
            if df is None or df.empty:
                return json.dumps({"success": False, "error": "No data in shared state for this symbol/timeframe"})

            # Use last N candles
            plot_df = df.tail(candles).copy()
            plot_df = plot_df.set_index("time")
            plot_df.index = pd.DatetimeIndex(plot_df.index)

            # Ensure column names match what mplfinance expects (lowercase)
            plot_df.columns = [c.lower() for c in plot_df.columns]

            # Technical overlay lines / Các đường chỉ báo kỹ thuật
            add_plots = []

            # SMA 20 & 50 / SMA 20 & 50
            if len(plot_df) >= 50:
                sma20 = plot_df["close"].rolling(20).mean()
                sma50 = plot_df["close"].rolling(50).mean()
                add_plots.append(mpf.make_addplot(sma20, color="blue", width=0.8, label="SMA20"))
                add_plots.append(mpf.make_addplot(sma50, color="orange", width=0.8, label="SMA50"))

            # EMA 9 / EMA 9
            if len(plot_df) >= 9:
                ema9 = plot_df["close"].ewm(span=9).mean()
                add_plots.append(mpf.make_addplot(ema9, color="cyan", width=0.8, label="EMA9"))

            # Bollinger Bands (20, 2σ) / Dải Bollinger (20, 2σ)
            if len(plot_df) >= 20:
                bb_mid = plot_df["close"].rolling(20).mean()
                bb_std = plot_df["close"].rolling(20).std()
                bb_upper = bb_mid + 2 * bb_std
                bb_lower = bb_mid - 2 * bb_std
                add_plots.append(mpf.make_addplot(bb_upper, color="gray", linestyle="--", width=0.6))
                add_plots.append(mpf.make_addplot(bb_lower, color="gray", linestyle="--", width=0.6))

            Path(output_dir).mkdir(parents=True, exist_ok=True)
            out_path = os.path.join(output_dir, f"current_{symbol}_{timeframe}.png")

            mpf.plot(
                plot_df,
                type="candle",
                style="nightclouds",
                title=f"{symbol} {timeframe} — {len(plot_df)} candles",
                volume=True,
                addplot=add_plots if add_plots else [],
                figsize=(14, 8),
                tight_layout=True,
                savefig=dict(fname=out_path, dpi=150, bbox_inches="tight"),
            )

            logger.info("Chart saved", path=out_path, symbol=symbol, timeframe=timeframe)
            return json.dumps({
                "success": True,
                "chart_path": out_path,
                "symbol": symbol,
                "timeframe": timeframe,
                "candles_plotted": len(plot_df),
            })

        except Exception as e:
            logger.error("Chart generation failed", error=str(e))
            return json.dumps({"success": False, "error": str(e)})


# ────────────────────────────────────────────────────────────────────────────
# Plotly interactive chart (HTML)
# ────────────────────────────────────────────────────────────────────────────

class _PlotlyInput(BaseModel):
    symbol: str = Field(description="Currency pair symbol")
    timeframe: str = Field(description="Timeframe string")
    candles: int = Field(default=200, description="Number of candles to include")
    output_dir: str = Field(default="./charts", description="Directory to save HTML file")


class GeneratePlotlyChartTool(BaseTool):
    """
    Generate an interactive Plotly HTML candlestick chart.
    Tạo biểu đồ nến HTML Plotly tương tác.
    """

    name: str = "generate_plotly_chart"
    description: str = (
        "Generate an interactive Plotly candlestick HTML chart with SMA/EMA overlays "
        "and volume bar subplots. Saves to ./charts/ and returns the file path."
    )
    args_schema: Type[BaseModel] = _PlotlyInput

    def _run(
        self,
        symbol: str,
        timeframe: str,
        candles: int = 200,
        output_dir: str = "./charts",
    ) -> str:
        from utils.shared_state import shared_state

        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            df = shared_state.get_df(symbol, timeframe)
            if df is None or df.empty:
                return json.dumps({"success": False, "error": "No data available"})

            plot_df = df.tail(candles).copy()

            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True,
                row_heights=[0.75, 0.25],
                vertical_spacing=0.03,
            )

            # Candlestick trace / Dấu vết nến
            fig.add_trace(
                go.Candlestick(
                    x=plot_df["time"],
                    open=plot_df["open"],
                    high=plot_df["high"],
                    low=plot_df["low"],
                    close=plot_df["close"],
                    name=symbol,
                    increasing_line_color="#26a69a",
                    decreasing_line_color="#ef5350",
                ),
                row=1, col=1,
            )

            # SMA overlays / Lớp phủ SMA
            for period, color in [(20, "#2196F3"), (50, "#FF9800")]:
                if len(plot_df) >= period:
                    fig.add_trace(
                        go.Scatter(
                            x=plot_df["time"],
                            y=plot_df["close"].rolling(period).mean(),
                            name=f"SMA{period}",
                            line=dict(color=color, width=1),
                        ),
                        row=1, col=1,
                    )

            # Volume bars / Thanh khối lượng
            colors = [
                "#26a69a" if c >= o else "#ef5350"
                for c, o in zip(plot_df["close"], plot_df["open"])
            ]
            fig.add_trace(
                go.Bar(x=plot_df["time"], y=plot_df["volume"], name="Volume", marker_color=colors),
                row=2, col=1,
            )

            fig.update_layout(
                title=f"{symbol} {timeframe}",
                template="plotly_dark",
                height=700,
                xaxis_rangeslider_visible=False,
                showlegend=True,
            )

            Path(output_dir).mkdir(parents=True, exist_ok=True)
            out_path = os.path.join(output_dir, f"interactive_{symbol}_{timeframe}.html")
            fig.write_html(out_path)

            return json.dumps({
                "success": True,
                "chart_path": out_path,
                "symbol": symbol,
                "timeframe": timeframe,
            })

        except Exception as e:
            logger.error("Plotly chart failed", error=str(e))
            return json.dumps({"success": False, "error": str(e)})
