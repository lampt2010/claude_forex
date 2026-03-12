# 📈 Forex Trading Bot — 5-Agent CrewAI System

A fully automated Forex trading system powered by **5 CrewAI agents**, MetaTrader 5, computer vision pattern recognition (SSIM + pHash + CLIP), and LLM-based trade decision making.

---

## 🏗️ Architecture

```
main.py  →  CrewAI Sequential Crew
             │
             ├── 1. DataCollectorAgent   (Senior MT5 Data Engineer)
             │       └─ mt5_connect, mt5_fetch_data, mt5_account_info
             │
             ├── 2. VisualizerAgent      (Real-time Charting Specialist)
             │       └─ generate_candlestick_chart, generate_plotly_chart
             │
             ├── 3. PatternAnalyzerAgent (Chart Pattern Recognition Expert)
             │       └─ pattern_match (SSIM + pHash + CLIP), support_resistance
             │
             ├── 4. TradeDeciderAgent    (Senior Forex Trader & Risk Manager)
             │       └─ calculate_indicators, mt5_account_info,
             │          mt5_get_positions, mt5_place_order
             │
             └── 5. StatisticianAgent   (Performance Analyst & Reporter)
                     └─ generate_html_report, generate_pdf_report
```

**Data sharing between agents:**
- `utils/shared_state.py` — in-process singleton holding DataFrames
- SQLite database — persistence across restarts
- `./charts/` — PNG files passed from Visualizer → PatternAnalyzer

---

## 📂 Project Structure

```
forex_trading_bot/
├── main.py                     # Orchestrator + CLI entry point
├── config.yaml                 # All runtime configuration
├── .env.example                # Environment variable template
├── requirements.txt            # Python dependencies
│
├── agents/
│   ├── data_collector.py       # DataCollectorAgent
│   ├── visualizer.py           # VisualizerAgent
│   ├── pattern_analyzer.py     # PatternAnalyzerAgent
│   ├── trade_decider.py        # TradeDeciderAgent
│   └── statistician.py        # StatisticianAgent
│
├── tools/
│   ├── mt5_tools.py            # MT5 connection, data, orders
│   ├── chart_tools.py          # mplfinance + Plotly charts
│   ├── pattern_tools.py        # SSIM + pHash + CLIP matching
│   ├── indicator_tools.py      # pandas_ta indicators
│   └── report_tools.py        # HTML + PDF reports
│
├── utils/
│   ├── shared_state.py         # Singleton in-memory data cache
│   ├── database.py             # SQLite via SQLAlchemy
│   ├── logger.py               # structlog setup
│   └── telegram.py            # Telegram notifications
│
├── dashboard/
│   └── streamlit_app.py        # Live Streamlit dashboard
│
├── charts/                     # Generated PNG charts (auto-created)
├── patterns/                   # YOUR reference pattern images ← add here!
├── reports/                    # Generated HTML/PDF reports
└── logs/                       # Rotating log files
```

---

## ⚙️ Installation

### 1. Prerequisites

- **Windows 10/11** (MetaTrader5 package is Windows-only)
- **Python 3.10–3.12**
- **MetaTrader 5 terminal** installed and running
- An MT5 demo or live account

### 2. Clone / create the project

```bash
cd forex_trading_bot
```

### 3. Create virtual environment

```bash
python -m venv venv
venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

> ⚠️ `torch` is large (~2 GB). For CPU-only:
> ```bash
> pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
> ```

### 5. Configure environment

```bash
copy .env.example .env
```

Edit `.env` with your credentials:
```env
MT5_LOGIN=123456789
MT5_PASSWORD=your_password
MT5_SERVER=ICMarkets-Demo
OPENAI_API_KEY=sk-...
```

### 6. Configure trading parameters

Edit `config.yaml`:
- `trading.symbols` — currency pairs to trade
- `trading.timeframes` — timeframes to analyse
- `trading.risk_percent` — risk per trade (%)
- `llm.provider` / `llm.model` — your LLM backend

### 7. Add pattern images

Place chart pattern PNG images into `./patterns/`:
```
patterns/
├── hammer.png
├── shooting_star.png
├── bullish_engulfing.png
├── bearish_engulfing.png
├── morning_star.png
├── evening_star.png
├── head_and_shoulders.png
├── double_top.png
├── double_bottom.png
├── ascending_triangle.png
├── descending_triangle.png
└── bull_flag.png
```

You can find free pattern examples on TradingView screenshots or pattern libraries.

---

## 🚀 Usage

### Start MT5 terminal first!

Make sure MetaTrader 5 is open and logged in before running the bot.

### Run the bot (continuous loop)

```bash
python main.py
```

### Run a single cycle (for testing)

```bash
python main.py --once
```

### Use a custom config file

```bash
python main.py --config my_config.yaml
```

### Generate performance report only

```bash
python main.py --report-only
```

### Launch the live dashboard

```bash
streamlit run dashboard/streamlit_app.py
```

Open: http://localhost:8501

---

## 📊 Performance Metrics Tracked

| Metric | Description |
|--------|-------------|
| Win Rate | % of closed trades in profit |
| Profit Factor | Gross profit / gross loss |
| Total P/L | Net profit/loss in account currency |
| Max Drawdown | Largest peak-to-trough decline |
| Sharpe Ratio | Risk-adjusted return (annualised) |
| Monthly P/L | Breakdown by month |

---

## 🤖 LLM Providers

| Provider | `llm.provider` | Model examples |
|----------|---------------|----------------|
| OpenAI | `openai` | `gpt-4o`, `gpt-4o-mini` |
| Anthropic | `anthropic` | `claude-opus-4-6`, `claude-sonnet-4-6` |
| Groq (fast) | `groq` | `llama-3.3-70b-versatile`, `mixtral-8x7b-32768` |

---

## ⚠️ Risk Warning

> **IMPORTANT**: This software is for **educational and research purposes only**.
> Automated trading involves significant financial risk. Past performance does not
> guarantee future results. Always test on a **demo account** first.
> Never risk money you cannot afford to lose.

---

## 📝 Logs

Logs are written to `./logs/trading_bot.log` (rotating, max 10 MB × 5 files).

Set `logging.level: DEBUG` in `config.yaml` for verbose output.

---

## 🔧 Troubleshooting

**MT5 not connecting:**
- Ensure MetaTrader 5 is running and logged in
- Check `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` in `.env`
- The bot will automatically fall back to **simulation mode** if MT5 is unavailable

**CLIP slow on first run:**
- First run downloads `openai/clip-vit-base-patch32` (~600 MB) from HuggingFace
- Subsequent runs use the cached model

**LLM rate limit errors:**
- Reduce `crew.max_rpm` in `config.yaml`
- Use a faster/cheaper model for testing (e.g. `gpt-4o-mini`)

**No pattern matches:**
- Add PNG images to `./patterns/` folder
- Lower `patterns.min_confidence` in `config.yaml`

---

## 📄 License

MIT License — see LICENSE file.

---

*Built with ❤️ using CrewAI, MetaTrader 5, pandas_ta, mplfinance, Plotly, CLIP, and Streamlit.*
