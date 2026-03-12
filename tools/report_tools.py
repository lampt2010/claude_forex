"""
Report Generation Tools — HTML and PDF performance reports
Công cụ tạo báo cáo — Báo cáo hiệu suất HTML và PDF

Generates:
  - HTML performance dashboard with trade table and metrics
  - PDF summary using fpdf2
  - Exports trades to CSV
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Type

import structlog
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# HTML Report Tool
# ────────────────────────────────────────────────────────────────────────────

class _ReportInput(BaseModel):
    output_dir: str = Field(default="./reports", description="Directory to save the report")
    title: str = Field(default="Forex Trading Bot — Performance Report", description="Report title")


class GenerateHTMLReportTool(BaseTool):
    """
    Generate an HTML performance report from trades in the database.
    Tạo báo cáo HTML hiệu suất từ các giao dịch trong cơ sở dữ liệu.
    """

    name: str = "generate_html_report"
    description: str = (
        "Generate an HTML performance report showing trade statistics, equity curve "
        "and individual trade table. Saves to ./reports/ and returns the file path."
    )
    args_schema: Type[BaseModel] = _ReportInput

    def _run(self, output_dir: str = "./reports", title: str = "Forex Trading Bot — Performance Report") -> str:
        from utils.database import Database

        db = Database()
        db.initialize()
        stats = db.get_performance_stats()
        trades = db.get_trades(limit=500)

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(output_dir, f"report_{timestamp}.html")

        html = _build_html(title, stats, trades)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Also export latest CSV / Cũng xuất CSV mới nhất
        db.export_trades_csv(os.path.join(output_dir, "trades.csv"))

        logger.info("HTML report generated", path=out_path)
        return json.dumps({"success": True, "report_path": out_path, "stats": stats})


# ────────────────────────────────────────────────────────────────────────────
# PDF Report Tool
# ────────────────────────────────────────────────────────────────────────────

class GeneratePDFReportTool(BaseTool):
    """
    Generate a PDF performance report using fpdf2.
    Tạo báo cáo PDF hiệu suất sử dụng fpdf2.
    """

    name: str = "generate_pdf_report"
    description: str = "Generate a PDF summary report of trading performance. Returns the saved file path."
    args_schema: Type[BaseModel] = _ReportInput

    def _run(self, output_dir: str = "./reports", title: str = "Forex Bot — Performance") -> str:
        from utils.database import Database

        try:
            from fpdf import FPDF
        except ImportError:
            return json.dumps({"error": "fpdf2 not installed. Run: pip install fpdf2"})

        db = Database()
        db.initialize()
        stats = db.get_performance_stats()
        trades = db.get_trades(limit=200)

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(output_dir, f"report_{timestamp}.pdf")

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Title / Tiêu đề
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 12, title, ln=True, align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")
        pdf.ln(6)

        # Key metrics / Số liệu chính
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 9, "Performance Summary", ln=True)
        pdf.set_font("Helvetica", "", 11)

        metrics = [
            ("Total Trades", stats.get("total_trades", 0)),
            ("Win Rate", f"{stats.get('win_rate', 0):.1f}%"),
            ("Total P/L", f"{stats.get('total_pnl', 0):.2f}"),
            ("Profit Factor", f"{stats.get('profit_factor', 0):.2f}"),
            ("Max Drawdown", f"{stats.get('max_drawdown', 0):.2f}"),
            ("Sharpe Ratio", f"{stats.get('sharpe_ratio', 0):.2f}"),
        ]
        for label, val in metrics:
            pdf.cell(70, 8, label + ":", border="B")
            pdf.cell(0, 8, str(val), border="B", ln=True)

        pdf.ln(8)

        # Trade table (last 20) / Bảng giao dịch (20 cái cuối)
        if trades:
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 9, "Recent Trades (last 20)", ln=True)
            pdf.set_font("Helvetica", "B", 9)
            headers = ["Symbol", "TF", "Type", "Entry", "SL", "TP", "Lot", "P/L", "Status"]
            widths = [20, 12, 12, 22, 22, 22, 14, 16, 18]
            for h, w in zip(headers, widths):
                pdf.cell(w, 7, h, border=1, align="C")
            pdf.ln()

            pdf.set_font("Helvetica", "", 8)
            for t in trades[:20]:
                row = [
                    str(t.get("symbol", "")),
                    str(t.get("timeframe", "")),
                    str(t.get("order_type", "")),
                    f"{t.get('entry_price', 0) or 0:.5f}",
                    f"{t.get('sl_price', 0) or 0:.5f}",
                    f"{t.get('tp_price', 0) or 0:.5f}",
                    f"{t.get('lot_size', 0) or 0:.2f}",
                    f"{t.get('pnl', 0) or 0:.2f}",
                    str(t.get("status", "")),
                ]
                for val, w in zip(row, widths):
                    pdf.cell(w, 6, val[:12], border=1, align="C")
                pdf.ln()

        pdf.output(out_path)
        logger.info("PDF report generated", path=out_path)
        return json.dumps({"success": True, "report_path": out_path})


# ────────────────────────────────────────────────────────────────────────────
# HTML builder / Trình tạo HTML
# ────────────────────────────────────────────────────────────────────────────

def _build_html(title: str, stats: Dict[str, Any], trades: List[Dict]) -> str:
    """Build a self-contained HTML report string."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    win_rate = stats.get("win_rate", 0)
    total_pnl = stats.get("total_pnl", 0)
    pnl_color = "#4caf50" if total_pnl >= 0 else "#f44336"

    metric_cards = ""
    metrics = [
        ("Total Trades", stats.get("total_trades", 0), "#2196F3"),
        ("Win Rate", f"{win_rate:.1f}%", "#4caf50" if win_rate >= 50 else "#f44336"),
        ("Total P/L", f"{total_pnl:.2f}", pnl_color),
        ("Profit Factor", f"{stats.get('profit_factor', 0):.2f}", "#FF9800"),
        ("Max Drawdown", f"{stats.get('max_drawdown', 0):.2f}", "#f44336"),
        ("Sharpe Ratio", f"{stats.get('sharpe_ratio', 0):.2f}", "#9C27B0"),
        ("Gross Profit", f"{stats.get('gross_profit', 0):.2f}", "#4caf50"),
        ("Gross Loss", f"{stats.get('gross_loss', 0):.2f}", "#f44336"),
    ]
    for label, val, color in metrics:
        metric_cards += f"""
        <div class="card">
            <div class="card-value" style="color:{color}">{val}</div>
            <div class="card-label">{label}</div>
        </div>"""

    trade_rows = ""
    for t in trades:
        pnl = t.get("pnl", 0) or 0
        row_class = "win" if pnl > 0 else "loss" if pnl < 0 else ""
        trade_rows += f"""
        <tr class="{row_class}">
            <td>{t.get('id','')}</td>
            <td>{t.get('symbol','')}</td>
            <td>{t.get('timeframe','')}</td>
            <td><span class="badge {'buy' if t.get('order_type','')=='BUY' else 'sell'}">{t.get('order_type','')}</span></td>
            <td>{t.get('entry_price',0) or 0:.5f}</td>
            <td>{t.get('sl_price',0) or 0:.5f}</td>
            <td>{t.get('tp_price',0) or 0:.5f}</td>
            <td>{t.get('lot_size',0) or 0:.2f}</td>
            <td>{t.get('pattern','') or ''}</td>
            <td style="color:{'#4caf50' if pnl >= 0 else '#f44336'}">{pnl:.2f}</td>
            <td>{t.get('status','')}</td>
            <td>{str(t.get('open_time',''))[:16]}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #121212; color: #e0e0e0; padding: 20px; }}
  h1 {{ text-align: center; color: #ffffff; margin-bottom: 6px; font-size: 1.8em; }}
  .subtitle {{ text-align: center; color: #888; margin-bottom: 24px; font-size: 0.9em; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 28px; justify-content: center; }}
  .card {{ background: #1e1e2e; border-radius: 10px; padding: 18px 22px; min-width: 140px; text-align: center; border: 1px solid #2a2a3e; }}
  .card-value {{ font-size: 1.6em; font-weight: 700; }}
  .card-label {{ font-size: 0.78em; color: #888; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
  h2 {{ color: #aaa; margin-bottom: 12px; font-size: 1.1em; }}
  table {{ width: 100%; border-collapse: collapse; background: #1a1a2e; border-radius: 8px; overflow: hidden; }}
  th {{ background: #262640; color: #ccc; padding: 10px 12px; font-size: 0.82em; text-align: left; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #2a2a3e; font-size: 0.82em; }}
  tr.win {{ background: rgba(76,175,80,0.07); }}
  tr.loss {{ background: rgba(244,67,54,0.07); }}
  tr:hover {{ background: rgba(255,255,255,0.04); }}
  .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 0.78em; font-weight: 600; }}
  .badge.buy {{ background: rgba(76,175,80,0.25); color: #4caf50; }}
  .badge.sell {{ background: rgba(244,67,54,0.25); color: #f44336; }}
  .section {{ margin-bottom: 32px; }}
</style>
</head>
<body>
<h1>📈 {title}</h1>
<p class="subtitle">Generated at {ts}</p>

<div class="section">
  <h2>KEY METRICS</h2>
  <div class="metrics">{metric_cards}</div>
</div>

<div class="section">
  <h2>TRADE HISTORY ({len(trades)} records)</h2>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Symbol</th><th>TF</th><th>Type</th>
        <th>Entry</th><th>SL</th><th>TP</th><th>Lot</th>
        <th>Pattern</th><th>P/L</th><th>Status</th><th>Opened</th>
      </tr>
    </thead>
    <tbody>{trade_rows}</tbody>
  </table>
</div>
</body>
</html>"""
