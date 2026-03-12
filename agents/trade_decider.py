"""
TradeDeciderAgent — Senior Forex Trader & Risk Manager
Agent Quyết Định Giao Dịch — Nhà Giao Dịch Forex Cao Cấp & Quản Lý Rủi Ro

Responsibilities / Trách nhiệm:
  - Receive pattern results + technical indicators
  - Apply trading rules + LLM reasoning to decide BUY/SELL/HOLD
  - Calculate lot size based on configured risk % per trade
  - Place order via MT5: market order + SL + TP (min R:R = 1:2)
  - Enforce daily loss limit
  - Support partial close, trailing stop, breakeven logic
"""

from __future__ import annotations

from typing import Any, Dict

from crewai import Agent, Task

from tools.indicator_tools import CalculateIndicatorsTool
from tools.mt5_tools import MT5AccountInfoTool, MT5GetPositionsTool, MT5PlaceOrderTool


def create_trade_decider_agent(config: Dict[str, Any]) -> Agent:
    """
    Build the TradeDeciderAgent with indicator + order tools.
    Xây dựng TradeDeciderAgent với công cụ chỉ báo + đặt lệnh.
    """
    from agents.data_collector import _get_llm

    llm = _get_llm(config)
    risk_pct = config.get("trading", {}).get("risk_percent", 1.0)
    max_loss = config.get("trading", {}).get("max_daily_loss_percent", 5.0)
    min_rr = config.get("trading", {}).get("min_rr_ratio", 2.0)
    max_pos = config.get("trading", {}).get("max_positions", 5)

    return Agent(
        role="Senior Forex Trader & Risk Manager",
        goal=(
            f"Analyse pattern recognition results and technical indicators to make disciplined "
            f"BUY, SELL, or HOLD decisions. "
            f"Rules to enforce:\n"
            f"  • Risk exactly {risk_pct}% of balance per trade\n"
            f"  • Minimum R:R ratio of {min_rr}:1\n"
            f"  • Maximum {max_pos} concurrent open positions\n"
            f"  • Never exceed {max_loss}% daily loss limit\n"
            f"  • Only trade when pattern confidence ≥ 60% AND indicators align\n"
            f"Place orders via mt5_place_order. Never trade against strong trend. "
            f"Always return a structured JSON decision."
        ),
        backstory=(
            "You are a veteran forex trader with 15 years of experience trading major and "
            "minor currency pairs. You have survived multiple market crashes by maintaining "
            "iron-clad risk management. You never let emotions override rules — if the setup "
            "is not perfect, you HOLD and wait for the next opportunity. "
            "Bạn là nhà giao dịch forex kỳ cựu với 15 năm kinh nghiệm, luôn tuân thủ nghiêm ngặt "
            "các quy tắc quản lý rủi ro và không bao giờ để cảm xúc chi phối quyết định."
        ),
        tools=[
            CalculateIndicatorsTool(),
            MT5AccountInfoTool(),
            MT5GetPositionsTool(),
            MT5PlaceOrderTool(),
        ],
        llm=llm,
        verbose=config.get("logging", {}).get("verbose", True),
        allow_delegation=False,
        max_iter=8,
    )


def create_trade_decision_task(
    agent: Agent,
    context: Dict[str, Any],
    config: Dict[str, Any],
) -> Task:
    """
    Create a trade decision + execution task.
    Tạo nhiệm vụ quyết định + thực thi giao dịch.
    """
    symbol = context["symbol"]
    timeframe = context["timeframe"]
    cycle = context.get("cycle", 0)

    risk_pct = config.get("trading", {}).get("risk_percent", 1.0)
    max_loss_pct = config.get("trading", {}).get("max_daily_loss_percent", 5.0)
    min_rr = config.get("trading", {}).get("min_rr_ratio", 2.0)
    max_pos = config.get("trading", {}).get("max_positions", 5)
    magic = config.get("mt5", {}).get("magic_number", 20241201)

    return Task(
        description=(
            f"Make a trading decision for {symbol} {timeframe} at cycle #{cycle}.\n\n"
            f"STEP 1 — Gather data:\n"
            f"  a. Use calculate_indicators for symbol='{symbol}', timeframe='{timeframe}' "
            f"     to get RSI, MACD, Bollinger, ATR, SMA/EMA values.\n"
            f"  b. Use mt5_account_info to get current balance and equity.\n"
            f"  c. Use mt5_get_positions to count open trades and check existing {symbol} exposure.\n\n"
            f"STEP 2 — Evaluate the setup:\n"
            f"  The previous task provided pattern analysis results (best pattern, confidence, "
            f"  SR context, trade bias). Use that context together with indicators.\n\n"
            f"  Apply ALL of these rules — HOLD if any rule is violated:\n"
            f"  ✅ Pattern confidence ≥ 60%\n"
            f"  ✅ Indicators (RSI, MACD, trend) must AGREE with pattern bias\n"
            f"  ✅ Not already at max {max_pos} open positions\n"
            f"  ✅ Daily loss has NOT exceeded {max_loss_pct}% of balance\n"
            f"  ✅ No existing open position for this symbol\n"
            f"  ✅ Pattern bias aligns with higher-timeframe trend\n\n"
            f"STEP 3 — If BUY or SELL, calculate lot size:\n"
            f"  Formula: lot_size = (balance × {risk_pct / 100}) / (sl_pips × pip_value)\n"
            f"  For majors: pip_value ≈ $10 per pip per standard lot (0.1 lot = $1/pip)\n"
            f"  Use ATR_14 × 1.5 as SL in pips; TP = SL × {min_rr} (R:R = 1:{min_rr})\n"
            f"  Round lot to 2 decimal places; minimum 0.01, maximum 5.00\n\n"
            f"STEP 4 — Execute:\n"
            f"  If BUY or SELL: use mt5_place_order with symbol='{symbol}', "
            f"  order_type=<BUY|SELL>, lot_size=<calculated>, sl_pips=<sl>, tp_pips=<tp>, "
            f"  magic={magic}.\n"
            f"  If HOLD: do NOT call mt5_place_order.\n\n"
            f"STEP 5 — Return JSON decision."
        ),
        expected_output=(
            "A JSON string with ALL of these fields:\n"
            "  decision: 'BUY' | 'SELL' | 'HOLD'\n"
            "  symbol, timeframe, cycle\n"
            "  entry_price (float or null)\n"
            "  sl_price (float or null), sl_pips (float or null)\n"
            "  tp_price (float or null), tp_pips (float or null)\n"
            "  lot_size (float or null)\n"
            "  rr_ratio (float)\n"
            "  ticket (int or null — from mt5_place_order)\n"
            "  pattern (string), pattern_confidence (float)\n"
            "  indicators_summary (string — brief description)\n"
            "  reason (string — detailed explanation of the decision)\n"
            "  risk_amount_usd (float or null)"
        ),
        agent=agent,
    )
