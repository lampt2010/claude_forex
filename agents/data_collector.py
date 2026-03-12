"""
DataCollectorAgent — Senior MT5 Data Engineer
Agent Thu Thập Dữ Liệu — Kỹ Sư Dữ Liệu MT5 Cao Cấp

Responsibilities / Trách nhiệm:
  - Connect to MetaTrader 5
  - Fetch real-time OHLCV for configured symbols & timeframes
  - Store in pandas DataFrame (shared state) + SQLite
  - Return a structured JSON summary of fetched data
"""

from __future__ import annotations

import os
from typing import Any, Dict

from crewai import Agent, Task

from tools.mt5_tools import MT5AccountInfoTool, MT5ConnectionTool, MT5FetchDataTool


def _get_llm(config: Dict[str, Any]):
    """
    Instantiate the LLM backend based on config using crewai.LLM.
    Khoi tao backend LLM dua tren cau hinh su dung crewai.LLM.
    Supports: openai, anthropic, groq
    """
    from crewai import LLM

    provider = config.get("llm", {}).get("provider", "groq").lower()
    model = config.get("llm", {}).get("model", "llama-3.3-70b-versatile")
    temperature = config.get("llm", {}).get("temperature", 0.1)

    if provider == "anthropic":
        return LLM(
            model=f"anthropic/{model}",
            temperature=temperature,
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        )
    elif provider == "groq":
        return LLM(
            model=f"groq/{model}",
            temperature=temperature,
            api_key=os.getenv("GROQ_API_KEY", ""),
        )
    else:  # openai
        return LLM(
            model=model,
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )


def create_data_collector_agent(config: Dict[str, Any]) -> Agent:
    """
    Build the DataCollectorAgent with MT5 tools.
    Xây dựng DataCollectorAgent với các công cụ MT5.
    """
    llm = _get_llm(config)

    return Agent(
        role="Senior MT5 Data Engineer",
        goal=(
            "Connect to MetaTrader 5, fetch the latest OHLCV candlestick data for all "
            "configured currency pairs and timeframes, persist data to SQLite, and return "
            "a clean JSON summary of what was collected."
        ),
        backstory=(
            "You are an expert in financial data pipelines with 10+ years connecting trading "
            "platforms to data systems. You handle MT5 API quirks, network timeouts, and data "
            "gaps without missing a beat. You always validate data quality before storing it. "
            "Bạn là chuyên gia về đường ống dữ liệu tài chính với hơn 10 năm kinh nghiệm kết nối "
            "các nền tảng giao dịch với hệ thống dữ liệu."
        ),
        tools=[
            MT5ConnectionTool(),
            MT5FetchDataTool(),
            MT5AccountInfoTool(),
        ],
        llm=llm,
        verbose=config.get("logging", {}).get("verbose", True),
        allow_delegation=False,
        max_iter=5,
    )


def create_data_collection_task(
    agent: Agent,
    context: Dict[str, Any],
    config: Dict[str, Any],
) -> Task:
    """
    Create a data collection task for a specific symbol + timeframe.
    Tạo nhiệm vụ thu thập dữ liệu cho một cặp tiền + khung thời gian cụ thể.
    """
    symbol = context["symbol"]
    timeframe = context["timeframe"]
    count = config.get("trading", {}).get("candles_count", 500)

    mt5_login = config.get("mt5", {}).get("login", 0)
    mt5_password = config.get("mt5", {}).get("password", "")
    mt5_server = config.get("mt5", {}).get("server", "")

    return Task(
        description=(
            f"Collect {count} candles of {timeframe} OHLCV data for {symbol}.\n\n"
            f"Steps:\n"
            f"1. Use mt5_connect to initialise the MT5 session "
            f"(login={mt5_login}, server={mt5_server}).\n"
            f"2. Use mt5_account_info to verify the account is active.\n"
            f"3. Use mt5_fetch_data with symbol='{symbol}', timeframe='{timeframe}', "
            f"count={count} to fetch and store the data.\n"
            f"4. Return a JSON object summarising: symbol, timeframe, candles_fetched, "
            f"latest_close, data_range, account_balance.\n\n"
            f"If MT5 is unavailable, the tool will automatically use simulation data — "
            f"continue and note this in the result."
        ),
        expected_output=(
            f"A JSON string with keys: symbol, timeframe, candles_fetched, latest_close, "
            f"latest_time, data_range, source (MT5 or SIMULATION), account_balance."
        ),
        agent=agent,
    )
