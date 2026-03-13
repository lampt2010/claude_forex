"""
VisualizerAgent — Real-time Charting Specialist
Agent Trực Quan Hóa — Chuyên Gia Vẽ Biểu Đồ Thời Gian Thực

Responsibilities / Trách nhiệm:
  - Read latest OHLCV from shared state
  - Generate mplfinance candlestick PNG (saved to ./charts/)
  - Optionally generate interactive Plotly HTML
  - Return file paths for downstream pattern analysis
"""

from __future__ import annotations

from typing import Any, Dict

from crewai import Agent, Task
from utils.llm_factory import get_llm

from tools.chart_tools import GenerateCandlestickChartTool, GeneratePlotlyChartTool


def create_visualizer_agent(config: Dict[str, Any]) -> Agent:
    """
    Build the VisualizerAgent with chart generation tools.
    Xây dựng VisualizerAgent với các công cụ tạo biểu đồ.
    """
    llm = get_llm(config)
    charts_dir = config.get("charts", {}).get("folder", "./charts")
    candle_count = config.get("charts", {}).get("candles_to_plot", 150)

    return Agent(
        role="Real-time Charting Specialist",
        goal=(
            "Take the latest OHLCV data from shared memory and generate professional-grade "
            "candlestick charts with technical indicator overlays. Save charts as PNG and HTML. "
            "Return the file paths so the pattern analyzer can use them."
        ),
        backstory=(
            "You are a professional financial data visualisation engineer who has built trading "
            "dashboards for hedge funds. You know how to make charts that reveal patterns clearly: "
            "the right colour scheme, timeframe, indicator overlays, and zoom level. "
            "Bạn là kỹ sư trực quan hóa dữ liệu tài chính chuyên nghiệp đã xây dựng bảng điều khiển "
            "giao dịch cho các quỹ phòng hộ."
        ),
        tools=[
            GenerateCandlestickChartTool(),
            GeneratePlotlyChartTool(),
        ],
        llm=llm,
        verbose=config.get("logging", {}).get("verbose", True),
        allow_delegation=False,
        max_iter=4,
    )


def create_visualization_task(
    agent: Agent,
    context: Dict[str, Any],
    config: Dict[str, Any],
) -> Task:
    """
    Create a chart generation task.
    Tạo nhiệm vụ tạo biểu đồ.
    """
    symbol = context["symbol"]
    timeframe = context["timeframe"]
    charts_dir = config.get("charts", {}).get("folder", "./charts")
    candles = config.get("charts", {}).get("candles_to_plot", 150)

    return Task(
        description=(
            f"Generate candlestick charts for {symbol} {timeframe}.\n\n"
            f"Steps:\n"
            f"1. Use generate_candlestick_chart with symbol='{symbol}', "
            f"timeframe='{timeframe}', candles={candles}, output_dir='{charts_dir}'.\n"
            f"   This produces: {charts_dir}/current_{symbol}_{timeframe}.png\n"
            f"2. Use generate_plotly_chart with the same parameters to produce an interactive HTML chart.\n"
            f"3. Return a JSON object with both file paths and the number of candles plotted.\n\n"
            f"Important: The PNG path is critical — the pattern analyzer needs it exactly as "
            f"'{charts_dir}/current_{symbol}_{timeframe}.png'."
        ),
        expected_output=(
            f"A JSON string with keys: png_path (e.g. '{charts_dir}/current_{symbol}_{timeframe}.png'), "
            f"html_path, symbol, timeframe, candles_plotted, indicators_shown."
        ),
        agent=agent,
    )
