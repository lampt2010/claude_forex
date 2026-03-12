"""
StatisticianAgent — Performance Analyst & Reporter
Agent Thống Kê — Nhà Phân Tích Hiệu Suất & Phóng Viên

Responsibilities / Trách nhiệm:
  - Record every trade decision to SQLite + CSV
  - Calculate Win Rate, Profit Factor, Max Drawdown, Sharpe Ratio, P/L
  - Generate HTML/PDF report (every 24h or on demand)
  - Send Telegram summary (optional)
  - Update shared state with latest stats
"""

from __future__ import annotations

from typing import Any, Dict

from crewai import Agent, Task

from tools.report_tools import GenerateHTMLReportTool, GeneratePDFReportTool


def create_statistician_agent(config: Dict[str, Any]) -> Agent:
    """
    Build the StatisticianAgent with reporting tools.
    Xây dựng StatisticianAgent với các công cụ báo cáo.
    """
    from agents.data_collector import _get_llm

    llm = _get_llm(config)
    report_fmt = config.get("reports", {}).get("format", "html")

    return Agent(
        role="Performance Analyst & Reporter",
        goal=(
            "Record every trade decision (BUY/SELL/HOLD) to the database and CSV. "
            "Calculate real-time performance metrics: win rate, profit factor, max drawdown, "
            "Sharpe ratio, total P/L, monthly breakdown. "
            "Generate a performance report when requested. "
            "Surface actionable insights about what patterns and conditions are working best."
        ),
        backstory=(
            "You are a quantitative analyst who has worked at a proprietary trading firm. "
            "You believe that meticulous record-keeping and honest statistical analysis are "
            "the foundation of profitable systematic trading. You track every trade, notice "
            "patterns in performance data, and help the team improve their edge over time. "
            "Bạn là nhà phân tích định lượng tin rằng việc ghi chép cẩn thận và phân tích "
            "thống kê trung thực là nền tảng của giao dịch hệ thống có lợi nhuận."
        ),
        tools=[
            GenerateHTMLReportTool(),
            GeneratePDFReportTool(),
        ],
        llm=llm,
        verbose=config.get("logging", {}).get("verbose", True),
        allow_delegation=False,
        max_iter=5,
    )


def create_statistics_task(
    agent: Agent,
    context: Dict[str, Any],
    config: Dict[str, Any],
) -> Task:
    """
    Create a trade recording + statistics task.
    Tạo nhiệm vụ ghi lại giao dịch + thống kê.
    """
    symbol = context["symbol"]
    timeframe = context["timeframe"]
    cycle = context.get("cycle", 0)
    reports_dir = config.get("reports", {}).get("folder", "./reports")
    report_fmt = config.get("reports", {}).get("format", "html")
    report_hours = config.get("reports", {}).get("generate_every_hours", 24)
    telegram_enabled = config.get("telegram", {}).get("enabled", False)
    telegram_token = config.get("telegram", {}).get("bot_token", "")
    telegram_chat = config.get("telegram", {}).get("chat_id", "")

    return Task(
        description=(
            f"Record and analyse trading activity for {symbol} {timeframe} at cycle #{cycle}.\n\n"
            f"STEP 1 — Record the trade decision:\n"
            f"  The previous task (TradeDeciderAgent) produced a JSON decision. Extract:\n"
            f"  decision, symbol, timeframe, entry_price, sl_price, tp_price, lot_size,\n"
            f"  pattern, pattern_confidence, reason, ticket, cycle.\n"
            f"  Save it to the database by calling the appropriate tool or noting the data.\n\n"
            f"STEP 2 — Compute statistics:\n"
            f"  Use generate_html_report (output_dir='{reports_dir}') to compute and display "
            f"  live statistics from ALL historical trades in the database.\n"
            f"  Key metrics to include in your summary:\n"
            f"    - Total trades, winning trades, losing trades\n"
            f"    - Win rate (%), Profit Factor, Total P/L\n"
            f"    - Max Drawdown, Sharpe Ratio\n"
            f"    - Today's P/L and trade count\n\n"
            f"STEP 3 — Generate report if needed:\n"
            f"  Generate a {report_fmt.upper()} report and save to '{reports_dir}'.\n\n"
            f"STEP 4 — Telegram notification (if enabled={telegram_enabled}):\n"
            f"  If telegram is enabled and a BUY/SELL was placed, note the alert details.\n\n"
            f"STEP 5 — Return a comprehensive statistics summary as JSON."
        ),
        expected_output=(
            "A JSON string with:\n"
            "  trade_recorded: bool\n"
            "  trade_id: int or null\n"
            "  current_stats: { total_trades, win_rate, total_pnl, profit_factor, "
            "max_drawdown, sharpe_ratio }\n"
            "  report_path: string (path to generated report)\n"
            "  cycle: int\n"
            "  symbol: string\n"
            "  timeframe: string\n"
            "  insights: string (1-2 sentence observation about recent performance)"
        ),
        agent=agent,
    )
