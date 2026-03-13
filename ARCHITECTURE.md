# Forex Trading Bot — Kiến Trúc & Cách Hoạt Động

## Tổng quan

Bot giao dịch Forex tự động sử dụng **5 AI agent** chạy nối tiếp nhau (CrewAI pipeline). Mỗi chu kỳ, bot lấy dữ liệu thật từ MetaTrader 5, phân tích biểu đồ, nhận diện mô hình giá, quyết định BUY/SELL/HOLD và ghi lại thống kê — tất cả hoàn toàn tự động.

```
MT5 Terminal ──► DataCollector ──► Visualizer ──► PatternAnalyzer ──► TradeDecider ──► Statistician
                      │                │                 │                  │               │
                   SQLite DB        PNG/HTML          Top 3 patterns    BUY/SELL/HOLD   Report HTML
                   shared_state     ./charts/         + S/R levels      + MT5 order     ./reports/
```

---

## Luồng chạy

### Vòng lặp chính (`main.py`)

```
Khởi động
    │
    ├── Load config.yaml
    ├── Setup logger
    ├── Init SQLite database
    │
    └── LOOP (mỗi interval_minutes phút)
            │
            ├── Với mỗi (symbol × timeframe):
            │       DataCollector → Visualizer → PatternAnalyzer → TradeDecider → Statistician
            │
            └── Chờ đến chu kỳ tiếp theo
```

**Chế độ chạy:**
| Lệnh | Mô tả |
|------|-------|
| `python main.py` | Vòng lặp liên tục |
| `python main.py --once` | Chạy 1 chu kỳ rồi dừng |
| `python main.py --report-only` | Chỉ tạo báo cáo, không giao dịch |

---

## 5 Agents

### 1. DataCollectorAgent — Thu thập dữ liệu

**Role:** Senior MT5 Data Engineer

**Làm gì:**
1. Kết nối MetaTrader 5 bằng credentials từ `.env`
2. Lấy N nến OHLCV (mặc định 500 nến) cho từng cặp tiền / timeframe
3. Lưu vào SQLite + `shared_state` để các agent sau dùng
4. Nếu MT5 không khả dụng → tự động dùng dữ liệu mô phỏng (random walk)

**Tools:** `mt5_connect`, `mt5_fetch_data`, `mt5_account_info`

**Output mẫu:**
```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "candles_fetched": 500,
  "latest_close": 1.14632,
  "source": "MT5",
  "account_balance": 9998.7
}
```

---

### 2. VisualizerAgent — Vẽ biểu đồ

**Role:** Real-time Charting Specialist

**Làm gì:**
1. Lấy OHLCV từ `shared_state`
2. Vẽ biểu đồ nến (candlestick) kèm chỉ báo kỹ thuật (SMA, volume)
3. Xuất ra 2 file:
   - `./charts/current_EURUSD_H1.png` — dùng cho PatternAnalyzer (SSIM/pHash/CLIP)
   - `./charts/interactive_EURUSD_H1.html` — biểu đồ Plotly tương tác

**Tools:** `generate_candlestick_chart`, `generate_plotly_chart`

---

### 3. PatternAnalyzerAgent — Nhận diện mô hình

**Role:** Chart Pattern Recognition Expert

**Làm gì:**
1. So sánh chart hiện tại với thư viện pattern (`./patterns/`)
2. Dùng 3 phương pháp song song:
   - **SSIM** — Structural Similarity (so pixel)
   - **pHash** — Perceptual Hash (so hình dạng)
   - **CLIP** — AI embedding (chính xác nhất, chậm nhất)
3. Phát hiện vùng hỗ trợ / kháng cự (S/R levels)
4. Kết hợp → cho ra top 3 mô hình khớp nhất + độ tin cậy (%)

**Tools:** `pattern_match`, `support_resistance`

**Output mẫu:**
```json
{
  "top_patterns": [
    {"name": "bullish_engulfing", "confidence": 0.78},
    {"name": "hammer", "confidence": 0.65}
  ],
  "bias": "bullish",
  "support_levels": [1.1440, 1.1420],
  "resistance_levels": [1.1480, 1.1510]
}
```

---

### 4. TradeDeciderAgent — Quyết định giao dịch

**Role:** Senior Forex Trader & Risk Manager

**Làm gì:**
1. Tính toán các chỉ báo kỹ thuật (RSI, MACD, Bollinger, ATR, Stochastic...)
2. Kết hợp với kết quả pattern + S/R → quyết định BUY/SELL/HOLD
3. Áp dụng các luật quản lý rủi ro:
   - Pattern confidence phải ≥ 60%
   - Tỷ lệ R:R ≥ 2:1 (TP ít nhất gấp đôi SL)
   - Rủi ro mỗi lệnh = 1% số dư tài khoản
   - Tối đa 5 lệnh mở đồng thời
   - Dừng giao dịch nếu thua lỗ trong ngày > 5%
4. Nếu BUY/SELL → gọi `mt5_place_order` đặt lệnh thật trên MT5

**Tools:** `calculate_indicators`, `mt5_account_info`, `mt5_get_positions`, `mt5_place_order`

**Output mẫu:**
```json
{
  "decision": "BUY",
  "symbol": "EURUSD",
  "entry": 1.14632,
  "sl": 1.14382,
  "tp": 1.15132,
  "lot_size": 0.05,
  "ticket": 123456,
  "reason": "Bullish engulfing tại support 1.1440, RSI 45, MACD bullish crossover"
}
```

---

### 5. StatisticianAgent — Thống kê & báo cáo

**Role:** Performance Analyst & Reporter

**Làm gì:**
1. Ghi kết quả trade vào SQLite
2. Tính các chỉ số hiệu suất: Win rate, Profit factor, Max drawdown, Sharpe ratio
3. Tạo báo cáo HTML / PDF mỗi 24 giờ vào `./reports/`
4. (Tùy chọn) Gửi thông báo qua Telegram

---

## Chia sẻ dữ liệu giữa các Agent

Agents không truyền dữ liệu trực tiếp cho nhau — thay vào đó dùng 3 cơ chế:

```
┌─────────────────────────────────────────────────────────┐
│  shared_state (in-memory, thread-safe singleton)        │
│  • OHLCV DataFrames                                     │
│  • Latest decisions / patterns / indicators             │
│  • Account balance / equity                             │
│  • Open tickets, daily P/L                              │
├─────────────────────────────────────────────────────────┤
│  SQLite (trading_bot.db)                                │
│  • candles  — lịch sử giá                              │
│  • trades   — lịch sử lệnh                             │
│  • performance — thống kê tổng hợp                     │
├─────────────────────────────────────────────────────────┤
│  Files (./charts/)                                      │
│  • current_SYMBOL_TF.png  — Visualizer → PatternAnalyzer│
│  • interactive_SYMBOL_TF.html — xem trên browser       │
└─────────────────────────────────────────────────────────┘
```

Ngoài ra, CrewAI **task context** cho phép mỗi agent thấy output text của agent trước trong cùng cycle.

---

## Cấu trúc thư mục

```
forex_trading_bot/
├── main.py                  # Entry point, vòng lặp chính
├── config.yaml              # Toàn bộ cấu hình
├── .env                     # Secrets (MT5, API keys, Telegram)
│
├── agents/
│   ├── data_collector.py    # Agent 1 — lấy dữ liệu MT5
│   ├── visualizer.py        # Agent 2 — vẽ biểu đồ
│   ├── pattern_analyzer.py  # Agent 3 — nhận diện mô hình
│   ├── trade_decider.py     # Agent 4 — quyết định & đặt lệnh
│   └── statistician.py      # Agent 5 — thống kê & báo cáo
│
├── tools/
│   ├── mt5_tools.py         # MT5 connection, fetch, place order...
│   ├── chart_tools.py       # Vẽ candlestick, Plotly
│   ├── pattern_tools.py     # SSIM, pHash, CLIP matching
│   ├── indicator_tools.py   # RSI, MACD, ATR, Bollinger...
│   └── report_tools.py      # Tạo HTML/PDF report
│
├── utils/
│   ├── shared_state.py      # Singleton chia sẻ dữ liệu
│   ├── database.py          # SQLite manager
│   └── logger.py            # Structured logging (structlog)
│
├── dashboard/
│   └── streamlit_app.py     # Web dashboard realtime
│
├── charts/                  # PNG + HTML biểu đồ (tự động tạo)
├── patterns/                # Thư viện mô hình giá tham chiếu
├── reports/                 # Báo cáo hiệu suất HTML/PDF
├── logs/
│   ├── trading_bot.log      # Structured JSON log
│   └── realtime_stdout.log  # Bot output khi chạy background
│
├── trading_bot.db           # SQLite database
├── start.bat                # Khởi động (hiện log trực tiếp)
├── start_background.bat     # Khởi động (chạy ẩn)
├── stop.bat                 # Dừng bot
└── status.bat               # Xem trạng thái + log gần nhất
```

---

## Cấu hình quan trọng (`config.yaml`)

```yaml
trading:
  symbols: [EURUSD]          # Cặp tiền giao dịch
  timeframes: [M5, H1]       # Timeframe phân tích
  interval_minutes: 5        # Tần suất chạy cycle
  candles_count: 500         # Số nến lấy mỗi lần
  risk_percent: 1.0          # Rủi ro mỗi lệnh (% tài khoản)
  max_daily_loss_percent: 5.0 # Dừng khi thua > 5%/ngày
  min_rr_ratio: 2.0          # Tỷ lệ R:R tối thiểu
  max_positions: 5           # Số lệnh mở tối đa

llm:
  provider: groq             # groq | openai | anthropic
  model: llama-3.3-70b-versatile
```

---

## Secrets (`.env`)

```
MT5_LOGIN=413343222
MT5_PASSWORD=...
MT5_SERVER=Exness-MT5Trial6

GROQ_API_KEY=gsk_...
OPENAI_API_KEY=sk-...       # Không dùng (provider=groq)
ANTHROPIC_API_KEY=sk-ant-...

TELEGRAM_BOT_TOKEN=         # Để trống nếu không dùng
TELEGRAM_CHAT_ID=
```

---

## Dashboard (Streamlit)

Chạy web dashboard để xem realtime:

```bash
cd forex_trading_bot
venv\Scripts\activate
streamlit run dashboard/streamlit_app.py
```

Mở trình duyệt tại `http://localhost:8501`

**Các tab:**
- KPI Cards: Win rate, P/L, Profit factor, Sharpe ratio
- Live candlestick chart (tự refresh)
- Lịch sử giao dịch (màu xanh=BUY, đỏ=SELL)
- Đường cong P/L tích lũy
- Top pattern matches

---

## LLM Backend

Mỗi agent dùng LLM để **lý luận** (reasoning) — quyết định tool nào gọi, đọc kết quả tool, tổng hợp kết luận cuối cùng.

| Provider | Model | Ghi chú |
|----------|-------|---------|
| **groq** (hiện tại) | llama-3.3-70b-versatile | Nhanh, miễn phí tier |
| openai | gpt-4o | Chính xác hơn, tốn phí |
| anthropic | claude-opus-4-6 | Tốt nhất, tốn phí nhiều nhất |

Đổi provider trong `config.yaml`:
```yaml
llm:
  provider: anthropic
  model: claude-opus-4-6
```

---

## Quản lý rủi ro

TradeDeciderAgent áp dụng **tất cả** các luật sau — vi phạm bất kỳ luật nào → HOLD:

1. **Pattern confidence ≥ 60%** — không giao dịch nếu mô hình không chắc
2. **R:R ≥ 2:1** — TP phải ít nhất gấp đôi SL
3. **Risk 1%/lệnh** — lot size tính tự động từ ATR và SL distance
4. **Max 5 lệnh** — không mở thêm nếu đã đủ
5. **Daily loss ≤ 5%** — dừng giao dịch cả ngày nếu vượt ngưỡng

---

## Vận hành

| File | Lệnh |
|------|------|
| Khởi động (xem log) | `start.bat` |
| Khởi động (nền) | `start_background.bat` |
| Dừng | `stop.bat` |
| Xem trạng thái | `status.bat` |
| Xem log realtime | `tail -f logs/realtime_stdout.log` |
| Dashboard web | `streamlit run dashboard/streamlit_app.py` |
| Báo cáo thủ công | `python main.py --report-only` |
| Test 1 cycle | `python main.py --once` |
