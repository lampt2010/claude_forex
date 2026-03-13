"""
Forex Trading Bot — Main Entry Point
Bot Giao Dịch Forex — Điểm Khởi Động Chính

Architecture / Kiến trúc:
  ┌─────────────────────────────────────────────────────────────┐
  │  DataCollectorAgent  → fetch OHLCV from MT5 or simulation   │
  │  VisualizerAgent     → generate candlestick charts (PNG)    │
  │  PatternAnalyzerAgent→ SSIM + pHash + CLIP pattern match   │
  │  TradeDeciderAgent   → indicators + LLM → BUY/SELL/HOLD    │
  │  StatisticianAgent   → record trade + performance report    │
  └─────────────────────────────────────────────────────────────┘

  All agents share data via:
  - utils/shared_state.py  (in-process DataFrames)
  - SQLite database         (persistence)
  - ./charts/               (PNG files between Visualizer → Analyzer)

Usage:
  python main.py
  python main.py --config custom_config.yaml
  python main.py --once          # run a single cycle and exit
  python main.py --report-only   # generate report and exit
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
import threading

# Force UTF-8 on Windows to handle emoji output from CrewAI / libraries
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Dict, Any

import structlog
import yaml
from dotenv import load_dotenv
from crewai import Crew, Process

# Load .env before anything else / Tải .env trước tất cả
load_dotenv()

# ────────────────────────────────────────────────────────────────────────────
# Graceful shutdown / Tắt máy nhẹ nhàng
# ────────────────────────────────────────────────────────────────────────────

_shutdown = threading.Event()


def _signal_handler(signum, frame):
    logger = structlog.get_logger()
    logger.warning("Shutdown signal received — finishing current cycle…", signal=signum)
    _shutdown.set()


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ────────────────────────────────────────────────────────────────────────────
# Config loader / Trình tải cấu hình
# ────────────────────────────────────────────────────────────────────────────

def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load YAML configuration file.
    Tải file cấu hình YAML.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ────────────────────────────────────────────────────────────────────────────
# Single trading cycle
# ────────────────────────────────────────────────────────────────────────────

def run_trading_cycle(config: Dict[str, Any], cycle_num: int) -> None:
    """
    Execute one complete analysis + decision cycle for all configured symbols.
    Thực thi một chu kỳ phân tích + quyết định hoàn chỉnh cho tất cả các cặp.

    For each (symbol, timeframe) pair the pipeline is:
      DataCollect → Visualize → AnalyzePattern → DecideTrade → RecordStats
    """
    from agents.data_collector import create_data_collector_agent, create_data_collection_task
    from agents.visualizer import create_visualizer_agent, create_visualization_task
    from agents.pattern_analyzer import create_pattern_analyzer_agent, create_pattern_analysis_task
    from agents.trade_decider import create_trade_decider_agent, create_trade_decision_task
    from agents.statistician import create_statistician_agent, create_statistics_task
    from utils.shared_state import shared_state

    logger = structlog.get_logger()
    shared_state.cycle = cycle_num

    symbols = config["trading"]["symbols"]
    timeframes = config["trading"]["timeframes"]

    # Reset daily counters at midnight / Reset bộ đếm hàng ngày vào nửa đêm
    now = datetime.now().time()
    if dtime(0, 0) <= now <= dtime(0, 5):
        shared_state.reset_daily()
        logger.info("Daily counters reset")

    # Create agents ONCE per cycle (stateless between cycles)
    # Tạo agent MỘT LẦN mỗi chu kỳ (không trạng thái giữa các chu kỳ)
    data_collector = create_data_collector_agent(config)
    visualizer = create_visualizer_agent(config)
    pattern_analyzer = create_pattern_analyzer_agent(config)
    trade_decider = create_trade_decider_agent(config)
    statistician = create_statistician_agent(config)

    all_tasks = []

    for symbol in symbols:
        for timeframe in timeframes:
            ctx = {"symbol": symbol, "timeframe": timeframe, "cycle": cycle_num}

            collect_task = create_data_collection_task(data_collector, ctx, config)
            viz_task = create_visualization_task(visualizer, ctx, config)
            analyze_task = create_pattern_analysis_task(pattern_analyzer, ctx, config)
            decide_task = create_trade_decision_task(trade_decider, ctx, config)
            stats_task = create_statistics_task(statistician, ctx, config)

            # Wire context so each task sees the output of the previous one
            # Kết nối context để mỗi task thấy đầu ra của task trước
            viz_task.context = [collect_task]
            analyze_task.context = [collect_task, viz_task]
            decide_task.context = [collect_task, analyze_task]
            stats_task.context = [decide_task]

            all_tasks.extend([collect_task, viz_task, analyze_task, decide_task, stats_task])

    crew = Crew(
        agents=[data_collector, visualizer, pattern_analyzer, trade_decider, statistician],
        tasks=all_tasks,
        process=Process.sequential,
        verbose=config.get("logging", {}).get("verbose", True),
        memory=config.get("crew", {}).get("memory", False),
        max_rpm=config.get("crew", {}).get("max_rpm", 10),
    )

    logger.info(
        "Running trading cycle",
        cycle=cycle_num,
        symbols=symbols,
        timeframes=timeframes,
        task_count=len(all_tasks),
    )

    result = crew.kickoff()
    logger.info("Cycle completed", cycle=cycle_num, summary=str(result)[:300])


# ────────────────────────────────────────────────────────────────────────────
# Report-only mode
# ────────────────────────────────────────────────────────────────────────────

def run_report_only(config: Dict[str, Any]) -> None:
    """
    Generate performance reports without trading.
    Tạo báo cáo hiệu suất mà không giao dịch.
    """
    from utils.database import Database

    logger = structlog.get_logger()
    db = Database(config["database"]["path"])
    db.initialize()
    stats = db.get_performance_stats()

    logger.info("Performance statistics", **stats)

    from tools.report_tools import GenerateHTMLReportTool, GeneratePDFReportTool

    reports_dir = config.get("reports", {}).get("folder", "./reports")
    fmt = config.get("reports", {}).get("format", "html")

    if fmt == "pdf":
        tool = GeneratePDFReportTool()
    else:
        tool = GenerateHTMLReportTool()

    result = tool._run(output_dir=reports_dir)
    logger.info("Report generated", result=result)


# ────────────────────────────────────────────────────────────────────────────
# Main loop / Vòng lặp chính
# ────────────────────────────────────────────────────────────────────────────

def main(args: argparse.Namespace) -> None:
    """
    Main entry point.
    Điểm khởi động chính.
    """
    config = load_config(args.config)

    # Setup structured logging / Cài đặt ghi nhật ký có cấu trúc
    from utils.logger import setup_logger
    setup_logger(config)
    logger = structlog.get_logger()

    # Ensure required directories exist / Đảm bảo các thư mục cần thiết tồn tại
    for d in ["charts", "patterns", "reports", "logs"]:
        Path(d).mkdir(exist_ok=True)

    # Initialise database / Khởi tạo cơ sở dữ liệu
    from utils.database import Database
    db = Database(config["database"]["path"])
    db.initialize()

    logger.info(
        "Forex Trading Bot starting",
        version="1.0.0",
        provider=config.get("llm", {}).get("provider", "openai"),
        symbols=config["trading"]["symbols"],
        timeframes=config["trading"]["timeframes"],
        interval_min=config["trading"]["interval_minutes"],
    )

    # Connect MT5 once — all tools reuse this single session
    # Kết nối MT5 một lần — tất cả tools dùng chung session này
    try:
        import MetaTrader5 as mt5
        import os as _os
        _login = int(_os.getenv("MT5_LOGIN", "0"))
        _password = _os.getenv("MT5_PASSWORD", "")
        _server = _os.getenv("MT5_SERVER", "")
        if mt5.initialize(login=_login, password=_password, server=_server):
            info = mt5.account_info()
            logger.info("MT5 connected", login=info.login, server=info.server, balance=info.balance)
        else:
            logger.warning("MT5 init failed — will run in simulation mode", error=str(mt5.last_error()))
    except ImportError:
        logger.warning("MetaTrader5 not installed — running in simulation mode")

    # ── report-only mode ──────────────────────────────────────────────────
    if args.report_only:
        run_report_only(config)
        db.close()
        return

    # ── single cycle mode ─────────────────────────────────────────────────
    if args.once:
        try:
            run_trading_cycle(config, cycle_num=1)
        except Exception as e:
            logger.error("Single cycle failed", error=str(e))
        db.close()
        return

    # ── continuous loop ───────────────────────────────────────────────────
    def _handle_rate_limit_and_retry(cfg, cnum, exc, log, max_attempts=4):
        """Vòng lặp retry: TPM → chờ 30s cùng key; TPD → rotate key."""
        from utils.llm_factory import rotate_groq_key, get_groq_keys
        last_err = exc
        for attempt in range(1, max_attempts + 1):
            err_str = str(last_err).lower()
            is_tpd = "per day" in err_str or "tokens per day" in err_str
            is_tpm = "per minute" in err_str or "tokens per minute" in err_str

            if is_tpd:
                new_key = rotate_groq_key()
                if not new_key:
                    log.error("All Groq keys exhausted for today", cycle=cnum)
                    return
                log.warning("TPD limit — rotated key", attempt=attempt,
                            cycle=cnum, total_keys=len(get_groq_keys()))
            elif is_tpm:
                log.warning("TPM limit — waiting 30s before retry",
                            attempt=attempt, cycle=cnum)
                time.sleep(30)
            else:
                log.error("Rate limit unknown type", error=str(last_err), cycle=cnum)
                return

            try:
                run_trading_cycle(cfg, cnum)
                return  # thành công
            except Exception as e2:
                err2 = str(e2).lower()
                if "rate_limit" in err2 or "ratelimit" in err2 or "quota" in err2 or "429" in err2:
                    last_err = e2
                    continue
                log.error("Cycle error after retry", error=str(e2), cycle=cnum, attempt=attempt)
                return
        log.error("All retry attempts failed", cycle=cnum)

    interval_sec = config["trading"]["interval_minutes"] * 60
    cycle_num = 0

    while not _shutdown.is_set():
        cycle_num += 1
        cycle_start = time.monotonic()

        try:
            run_trading_cycle(config, cycle_num)
        except KeyboardInterrupt:
            _shutdown.set()
            break
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "rate_limit" in err_str or "ratelimit" in err_str or "quota" in err_str or "429" in err_str

            if is_rate_limit:
                _handle_rate_limit_and_retry(config, cycle_num, e, logger)
            else:
                logger.error("Cycle error — will retry next interval", error=str(e), cycle=cycle_num)

        elapsed = time.monotonic() - cycle_start
        wait_sec = max(0.0, interval_sec - elapsed)

        logger.info(
            "Cycle finished",
            cycle=cycle_num,
            elapsed_s=round(elapsed, 1),
            next_in_s=round(wait_sec, 0),
        )

        # Interruptible sleep / Ngủ có thể bị ngắt
        slept = 0.0
        while slept < wait_sec and not _shutdown.is_set():
            time.sleep(min(1.0, wait_sec - slept))
            slept += 1.0

    logger.info("Bot stopped gracefully. Goodbye!")
    db.close()
    try:
        import MetaTrader5 as mt5
        mt5.shutdown()
        logger.info("MT5 disconnected")
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────────────
# CLI entry / Điểm vào CLI
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Forex Trading Bot — 5-Agent CrewAI system"
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to YAML config file (default: config.yaml)"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single trading cycle and exit"
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Generate performance report from existing data and exit"
    )
    main(parser.parse_args())
