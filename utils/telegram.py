"""
Telegram notification helper
Trợ giúp thông báo Telegram

Sends trade alerts and daily summaries to a Telegram chat.
Gửi cảnh báo giao dịch và tóm tắt hàng ngày đến một cuộc trò chuyện Telegram.
"""

from __future__ import annotations

import os
from typing import Optional

import requests
import structlog

logger = structlog.get_logger(__name__)


class TelegramNotifier:
    """
    Simple Telegram Bot API wrapper.
    Wrapper đơn giản cho Telegram Bot API.
    """

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"
    PHOTO_URL = "https://api.telegram.org/bot{token}/sendPhoto"

    def __init__(self, token: str = "", chat_id: str = "", enabled: bool = False) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = enabled and bool(self.token) and bool(self.chat_id)

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Send a text message.
        Gửi tin nhắn văn bản.
        """
        if not self.enabled:
            logger.debug("Telegram disabled, skipping message")
            return False

        try:
            url = self.BASE_URL.format(token=self.token)
            response = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode},
                timeout=10,
            )
            if not response.ok:
                logger.warning("Telegram send failed", status=response.status_code, body=response.text)
                return False
            logger.debug("Telegram message sent")
            return True
        except Exception as e:
            logger.error("Telegram error", error=str(e))
            return False

    def send_trade_alert(
        self,
        symbol: str,
        action: str,
        entry: float,
        sl: float,
        tp: float,
        lot: float,
        pattern: str,
        confidence: float,
    ) -> bool:
        """
        Format and send a trade alert message.
        Định dạng và gửi tin nhắn cảnh báo giao dịch.
        """
        emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⏸️"
        message = (
            f"{emoji} *TRADE ALERT*\n"
            f"Symbol: `{symbol}`\n"
            f"Action: *{action}*\n"
            f"Entry: `{entry:.5f}`\n"
            f"SL: `{sl:.5f}`\n"
            f"TP: `{tp:.5f}`\n"
            f"Lot: `{lot}`\n"
            f"Pattern: _{pattern}_ ({confidence:.0f}%)"
        )
        return self.send_message(message)

    def send_daily_summary(self, stats: dict) -> bool:
        """
        Send a formatted daily performance summary.
        Gửi bản tóm tắt hiệu suất hàng ngày được định dạng.
        """
        message = (
            "📊 *DAILY PERFORMANCE SUMMARY*\n"
            f"Trades: `{stats.get('total_trades', 0)}`\n"
            f"Win Rate: `{stats.get('win_rate', 0):.1f}%`\n"
            f"Total P/L: `{stats.get('total_pnl', 0):.2f}`\n"
            f"Profit Factor: `{stats.get('profit_factor', 0):.2f}`\n"
            f"Max Drawdown: `{stats.get('max_drawdown', 0):.2f}`\n"
            f"Sharpe Ratio: `{stats.get('sharpe_ratio', 0):.2f}`"
        )
        return self.send_message(message)

    def send_photo(self, photo_path: str, caption: str = "") -> bool:
        """
        Send a chart image.
        Gửi ảnh biểu đồ.
        """
        if not self.enabled:
            return False
        try:
            url = self.PHOTO_URL.format(token=self.token)
            with open(photo_path, "rb") as f:
                response = requests.post(
                    url,
                    data={"chat_id": self.chat_id, "caption": caption},
                    files={"photo": f},
                    timeout=30,
                )
            return response.ok
        except Exception as e:
            logger.error("Telegram photo send failed", error=str(e))
            return False
