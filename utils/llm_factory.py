"""
LLM Factory with Groq key rotation.
Trả về crewai.LLM thật — CrewAI tương thích hoàn toàn.
Rotation được xử lý bên ngoài (main.py) khi bắt RateLimitError.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict

import structlog

logger = structlog.get_logger(__name__)

_lock = threading.Lock()
_current_key_index = 0


def get_groq_keys() -> list[str]:
    """Đọc tất cả GROQ_API_KEY* từ env, bỏ qua key trống."""
    keys = []
    k = os.getenv("GROQ_API_KEY", "")
    if k:
        keys.append(k)
    for i in range(2, 10):
        k = os.getenv(f"GROQ_API_KEY_{i}", "")
        if k:
            keys.append(k)
    return keys


def get_current_groq_key() -> str:
    keys = get_groq_keys()
    if not keys:
        return ""
    with _lock:
        idx = _current_key_index % len(keys)
    return keys[idx]


def rotate_groq_key() -> str | None:
    """Chuyển sang key tiếp theo. Trả về key mới, hoặc None nếu chỉ có 1 key."""
    global _current_key_index
    keys = get_groq_keys()
    if len(keys) <= 1:
        return None
    with _lock:
        _current_key_index = (_current_key_index + 1) % len(keys)
        new_key = keys[_current_key_index]
    logger.warning("Groq key rotated", key_index=_current_key_index, total_keys=len(keys))
    return new_key


def get_llm(config: Dict[str, Any]):
    """Khởi tạo crewai.LLM chuẩn — luôn tương thích với CrewAI Agent."""
    from crewai import LLM

    provider = config.get("llm", {}).get("provider", "groq").lower()
    model = config.get("llm", {}).get("model", "llama-3.3-70b-versatile")
    temperature = config.get("llm", {}).get("temperature", 0.1)

    if provider == "groq":
        keys = get_groq_keys()
        logger.info("Groq LLM initialized", total_keys=len(keys), model=model,
                    key_index=_current_key_index)
        return LLM(
            model=f"groq/{model}",
            temperature=temperature,
            api_key=get_current_groq_key(),
        )

    elif provider == "anthropic":
        return LLM(
            model=f"anthropic/{model}",
            temperature=temperature,
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        )

    else:  # openai
        return LLM(
            model=model,
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )
