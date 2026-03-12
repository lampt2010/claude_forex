"""
Structured logging setup using structlog
Cài đặt ghi nhật ký có cấu trúc sử dụng structlog

Provides console (colored in TTY) + rotating file handler.
Cung cấp console (màu sắc trong TTY) + handler file xoay vòng.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog


def setup_logger(config: dict) -> None:
    """
    Initialize structlog with dual output: console + rotating file.
    Khởi tạo structlog với đầu ra kép: console + file xoay vòng.

    Args:
        config: Full application config dict from config.yaml
    """
    log_cfg = config.get("logging", {})
    log_level_name: str = log_cfg.get("level", "INFO").upper()
    log_level: int = getattr(logging, log_level_name, logging.INFO)
    log_file: str = log_cfg.get("log_file", "./logs/trading_bot.log")

    # Ensure log directory exists / Đảm bảo thư mục log tồn tại
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    # Root logger setup / Cài đặt logger gốc
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers / Xóa handler hiện có
    root_logger.handlers.clear()

    # Console handler / Handler console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # Rotating file handler (10 MB max, keep 5 backups)
    # Handler file xoay vòng (tối đa 10 MB, giữ 5 bản sao lưu)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    root_logger.addHandler(file_handler)

    # Determine renderer: colorful in interactive terminals, JSON in files/CI
    # Xác định renderer: màu sắc trong terminal tương tác, JSON trong file/CI
    use_json = not sys.stderr.isatty()
    renderer = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="ISO", utc=False),
            structlog.stdlib.add_logger_name,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
