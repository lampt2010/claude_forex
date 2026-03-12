"""
Streamlit Live Dashboard — Forex Trading Bot
Bảng Điều Khiển Trực Tiếp Streamlit — Bot Giao Dịch Forex

Run:
  streamlit run dashboard/streamlit_app.py

Features / Tính năng:
  - Live candlestick charts for each symbol/timeframe
  - Performance metrics (win rate, P/L, drawdown, Sharpe)
  - Trade history table with P/L colouring
  - Latest pattern detection results
  - Open positions monitor
  - Auto-refresh every N seconds
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# Allow imports from project root / Cho phép import từ thư mục gốc dự án
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.database import Database
from utils.shared_state import shared_state


# ────────────────────────────────────────────────────────────────────────────
# Page config / Cấu hình trang
# ────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Forex Trading Bot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Dark theme CSS / CSS giao diện tối
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .metric-card {
        background: #1e2130;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        border: 1px solid #2d3148;
    }
    .metric-value { font-size: 1.8em; font-weight: bold; }
    .metric-label { color: #888; font-size: 0.8em; margin-top: 4px; }
    .positive { color: #4caf50; }
    .negative { color: #f44336; }
    .neutral  { color: #2196f3; }
</style>
""", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Sidebar / Thanh bên
# ────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Settings")

    db_path = st.text_input("Database path", value="./trading_bot.db")
    refresh_sec = st.slider("Auto-refresh (seconds)", 10, 300, 30)
    charts_dir = st.text_input("Charts folder", value="./charts")

    st.divider()
    st.markdown("**Symbol Filter**")
    all_symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD"]
    selected_symbols = st.multiselect("Symbols", all_symbols, default=all_symbols[:3])

    all_tfs = ["M5", "M15", "H1", "H4"]
    selected_tf = st.selectbox("Timeframe", all_tfs, index=2)

    st.divider()
    st.caption(f"🔄 Refreshes every {refresh_sec}s")
    st.caption(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")

    if st.button("🔄 Refresh Now"):
        st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# Data loading / Tải dữ liệu
# ────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_db(path: str) -> Database:
    db = Database(path)
    db.initialize()
    return db


db = get_db(db_path)


@st.cache_data(ttl=refresh_sec)
def load_stats() -> Dict:
    return db.get_performance_stats()


@st.cache_data(ttl=refresh_sec)
def load_trades(limit: int = 200) -> pd.DataFrame:
    trades = db.get_trades(limit=limit)
    return pd.DataFrame(trades) if trades else pd.DataFrame()


@st.cache_data(ttl=refresh_sec)
def load_candles(symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
    return db.get_candles(symbol, timeframe, limit)


# ────────────────────────────────────────────────────────────────────────────
# Header / Tiêu đề
# ────────────────────────────────────────────────────────────────────────────

st.title("📈 Forex Trading Bot — Live Dashboard")
st.caption(f"Cycle: #{shared_state.cycle} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ────────────────────────────────────────────────────────────────────────────
# KPI Metrics / Số liệu KPI
# ────────────────────────────────────────────────────────────────────────────

stats = load_stats()

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    st.metric("Total Trades", stats.get("total_trades", 0))
with col2:
    wr = stats.get("win_rate", 0)
    st.metric("Win Rate", f"{wr:.1f}%", delta=f"{wr - 50:.1f}% vs 50%")
with col3:
    pnl = stats.get("total_pnl", 0)
    st.metric("Total P/L", f"${pnl:.2f}", delta=f"${pnl:.2f}")
with col4:
    st.metric("Profit Factor", f"{stats.get('profit_factor', 0):.2f}")
with col5:
    dd = stats.get("max_drawdown", 0)
    st.metric("Max Drawdown", f"${dd:.2f}")
with col6:
    st.metric("Sharpe Ratio", f"{stats.get('sharpe_ratio', 0):.2f}")

st.divider()


# ────────────────────────────────────────────────────────────────────────────
# Live Chart / Biểu đồ trực tiếp
# ────────────────────────────────────────────────────────────────────────────

st.subheader("📊 Live Candlestick Charts")

chart_tabs = st.tabs([f"{s} {selected_tf}" for s in selected_symbols])

for tab, symbol in zip(chart_tabs, selected_symbols):
    with tab:
        # Try loading from saved PNG first
        png_path = Path(charts_dir) / f"current_{symbol}_{selected_tf}.png"
        if png_path.exists():
            col_img, col_info = st.columns([3, 1])
            with col_img:
                st.image(str(png_path), use_container_width=True, caption=f"{symbol} {selected_tf}")
            with col_info:
                df = shared_state.get_df(symbol, selected_tf)
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    st.metric("Close", f"{latest['close']:.5f}")
                    change = latest["close"] - df.iloc[-2]["close"] if len(df) > 1 else 0
                    pct = change / df.iloc[-2]["close"] * 100 if len(df) > 1 else 0
                    st.metric("Change", f"{change:+.5f}", delta=f"{pct:+.2f}%")
                    st.metric("High", f"{latest['high']:.5f}")
                    st.metric("Low", f"{latest['low']:.5f}")
                    st.metric("Volume", f"{latest['volume']:.0f}")

                    # Latest indicators / Chỉ báo mới nhất
                    key = f"{symbol}_{selected_tf}"
                    ind = shared_state.latest_indicators.get(key, {})
                    if ind:
                        st.markdown("**Indicators**")
                        if "rsi_14" in ind:
                            rsi = ind["rsi_14"]
                            color = "🔴" if rsi > 70 else "🟢" if rsi < 30 else "🟡"
                            st.write(f"{color} RSI: {rsi:.1f}")
                        if "macd_histogram" in ind:
                            hist = ind["macd_histogram"] or 0
                            st.write(f"{'📈' if hist > 0 else '📉'} MACD Hist: {hist:.5f}")
                        if "trend" in ind:
                            st.write(f"Trend: **{ind['trend'].upper()}**")
        else:
            # Build Plotly chart from database
            df = load_candles(symbol, selected_tf, 200)
            if not df.empty:
                fig = _build_plotly_chart(df, symbol, selected_tf)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"No data yet for {symbol} {selected_tf}. Start the bot to collect data.")

st.divider()


# ────────────────────────────────────────────────────────────────────────────
# Trade History / Lịch sử giao dịch
# ────────────────────────────────────────────────────────────────────────────

st.subheader("📋 Trade History")

trades_df = load_trades(200)
if not trades_df.empty:
    # Format and colour / Định dạng và tô màu
    display_cols = [
        "id", "symbol", "timeframe", "order_type",
        "entry_price", "sl_price", "tp_price", "lot_size",
        "pattern", "pattern_confidence", "pnl", "status", "open_time"
    ]
    display_cols = [c for c in display_cols if c in trades_df.columns]
    display_df = trades_df[display_cols].copy()

    if "pnl" in display_df.columns:
        display_df["pnl"] = display_df["pnl"].fillna(0)

    def _colour_pnl(val):
        if pd.isna(val) or val == 0:
            return ""
        return "color: #4caf50" if val > 0 else "color: #f44336"

    def _colour_type(val):
        if val == "BUY":
            return "color: #4caf50; font-weight: bold"
        elif val == "SELL":
            return "color: #f44336; font-weight: bold"
        return ""

    styled = display_df.style
    if "pnl" in display_df.columns:
        styled = styled.applymap(_colour_pnl, subset=["pnl"])
    if "order_type" in display_df.columns:
        styled = styled.applymap(_colour_type, subset=["order_type"])

    st.dataframe(styled, use_container_width=True, height=400)

    # P/L distribution chart / Biểu đồ phân phối P/L
    if "pnl" in trades_df.columns:
        col_chart, col_hist = st.columns(2)
        with col_chart:
            # Cumulative P/L curve / Đường cong P/L tích lũy
            closed = trades_df[trades_df.get("status", pd.Series()) == "CLOSED"] if "status" in trades_df.columns else trades_df
            if not closed.empty and "pnl" in closed.columns:
                cum_pnl = closed["pnl"].fillna(0).cumsum()
                fig_cum = go.Figure()
                fig_cum.add_trace(go.Scatter(
                    y=cum_pnl.values,
                    mode="lines",
                    fill="tozeroy",
                    fillcolor="rgba(76,175,80,0.15)" if cum_pnl.iloc[-1] >= 0 else "rgba(244,67,54,0.15)",
                    line=dict(color="#4caf50" if cum_pnl.iloc[-1] >= 0 else "#f44336", width=2),
                    name="Cumulative P/L",
                ))
                fig_cum.update_layout(
                    title="Cumulative P/L", template="plotly_dark",
                    height=300, margin=dict(t=35, b=20, l=20, r=20)
                )
                st.plotly_chart(fig_cum, use_container_width=True)

        with col_hist:
            # P/L histogram / Biểu đồ cột P/L
            if not closed.empty:
                fig_hist = go.Figure()
                fig_hist.add_trace(go.Histogram(
                    x=closed["pnl"].fillna(0),
                    nbinsx=20,
                    marker_color="#2196F3",
                    opacity=0.8,
                    name="P/L Distribution",
                ))
                fig_hist.update_layout(
                    title="P/L Distribution", template="plotly_dark",
                    height=300, margin=dict(t=35, b=20, l=20, r=20)
                )
                st.plotly_chart(fig_hist, use_container_width=True)
else:
    st.info("No trades recorded yet. The bot will populate this table as it runs.")

st.divider()


# ────────────────────────────────────────────────────────────────────────────
# Pattern Results / Kết quả nhận dạng mẫu
# ────────────────────────────────────────────────────────────────────────────

st.subheader("🔍 Latest Pattern Analysis")

pattern_cols = st.columns(len(selected_symbols))
for col, symbol in zip(pattern_cols, selected_symbols):
    with col:
        key = f"{symbol}_{selected_tf}"
        patterns = shared_state.latest_patterns.get(key, [])
        st.markdown(f"**{symbol}**")
        if patterns:
            for p in patterns[:3]:
                name = p.get("pattern", "Unknown")
                conf = p.get("confidence", 0)
                bar_color = "🟢" if conf >= 70 else "🟡" if conf >= 50 else "🔴"
                st.write(f"{bar_color} {name}: **{conf:.0f}%**")
                st.progress(int(conf))
        else:
            st.write("_No patterns detected_")

st.divider()


# ────────────────────────────────────────────────────────────────────────────
# Auto-refresh / Tự động làm mới
# ────────────────────────────────────────────────────────────────────────────

time.sleep(refresh_sec)
st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# Helper: Plotly chart builder
# ────────────────────────────────────────────────────────────────────────────

def _build_plotly_chart(df: pd.DataFrame, symbol: str, timeframe: str) -> go.Figure:
    """Build an inline Plotly candlestick chart from a DataFrame."""
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.04
    )
    fig.add_trace(
        go.Candlestick(
            x=df["time"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name=symbol,
            increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        ),
        row=1, col=1,
    )
    for p, c in [(20, "#2196F3"), (50, "#FF9800")]:
        if len(df) >= p:
            fig.add_trace(
                go.Scatter(
                    x=df["time"], y=df["close"].rolling(p).mean(),
                    name=f"SMA{p}", line=dict(color=c, width=1)
                ),
                row=1, col=1,
            )
    colors = ["#26a69a" if c >= o else "#ef5350" for c, o in zip(df["close"], df["open"])]
    fig.add_trace(
        go.Bar(x=df["time"], y=df["volume"], name="Volume", marker_color=colors, opacity=0.6),
        row=2, col=1,
    )
    fig.update_layout(
        title=f"{symbol} {timeframe}", template="plotly_dark", height=550,
        xaxis_rangeslider_visible=False, margin=dict(t=40, b=20, l=20, r=20)
    )
    return fig
