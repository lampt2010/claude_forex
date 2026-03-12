"""
Pattern Recognition Tools — Multi-method image similarity
Công cụ nhận dạng mẫu giá — Tương đồng hình ảnh đa phương pháp

Methods used / Các phương pháp được sử dụng:
  1. SSIM    – Structural Similarity Index (scikit-image)
  2. pHash   – Perceptual Hash (imagehash)
  3. CLIP    – Vision-Language Embedding (openai/clip-vit-base-patch32, transformers)

Also includes a Support/Resistance detector using price action.
Cũng bao gồm bộ phát hiện Hỗ trợ/Kháng cự sử dụng hành động giá.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

import numpy as np
import structlog
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Pattern Match Tool
# ────────────────────────────────────────────────────────────────────────────

class _PatternInput(BaseModel):
    chart_path: str = Field(description="Full path to the current chart PNG")
    patterns_dir: str = Field(default="./patterns", description="Folder containing reference pattern images")
    top_n: int = Field(default=3, description="Number of top matches to return")
    min_confidence: float = Field(default=0.25, description="Minimum confidence threshold (0–1)")


class PatternMatchTool(BaseTool):
    """
    Compare a chart image against a library of reference patterns using
    SSIM + perceptual hash + CLIP embeddings.
    So sánh ảnh biểu đồ với thư viện mẫu tham chiếu sử dụng SSIM + hash + CLIP.
    """

    name: str = "pattern_match"
    description: str = (
        "Compare the current chart PNG against reference pattern images in ./patterns/ "
        "using SSIM, perceptual hashing, and CLIP embeddings. "
        "Returns top N pattern matches with confidence percentages as JSON."
    )
    args_schema: Type[BaseModel] = _PatternInput

    def _run(
        self,
        chart_path: str,
        patterns_dir: str = "./patterns",
        top_n: int = 3,
        min_confidence: float = 0.25,
    ) -> str:
        if not os.path.isfile(chart_path):
            return json.dumps({"error": f"Chart not found: {chart_path}", "matches": []})

        pattern_files = _get_pattern_files(patterns_dir)
        if not pattern_files:
            logger.warning("No pattern images found", dir=patterns_dir)
            return json.dumps({
                "warning": f"No pattern images found in {patterns_dir}",
                "matches": [],
                "tip": "Add PNG images of chart patterns to the ./patterns/ folder",
            })

        scores: List[Dict] = []

        # --- Load query image once ---
        query_gray = _load_gray(chart_path)
        query_pil = _load_pil(chart_path)
        query_clip_feat = _clip_features(query_pil)

        for pfile in pattern_files:
            try:
                pattern_name = Path(pfile).stem.replace("_", " ").replace("-", " ").title()

                ref_gray = _load_gray(pfile)
                ref_pil = _load_pil(pfile)

                # 1. SSIM score / Điểm SSIM
                ssim_score = _ssim_score(query_gray, ref_gray)

                # 2. Perceptual hash similarity / Tương đồng hash cảm nhận
                phash_score = _phash_score(query_pil, ref_pil)

                # 3. CLIP cosine similarity / Tương đồng cosine CLIP
                ref_clip_feat = _clip_features(ref_pil)
                clip_score = _cosine_similarity(query_clip_feat, ref_clip_feat) if (
                    query_clip_feat is not None and ref_clip_feat is not None
                ) else 0.0

                # Weighted ensemble / Tổng hợp có trọng số
                # CLIP gets most weight when available (semantically richer)
                if clip_score > 0:
                    combined = 0.30 * ssim_score + 0.20 * phash_score + 0.50 * clip_score
                else:
                    combined = 0.50 * ssim_score + 0.50 * phash_score

                scores.append({
                    "pattern": pattern_name,
                    "file": pfile,
                    "confidence": round(float(combined) * 100, 1),
                    "ssim": round(float(ssim_score) * 100, 1),
                    "phash": round(float(phash_score) * 100, 1),
                    "clip": round(float(clip_score) * 100, 1),
                })
            except Exception as exc:
                logger.warning("Pattern comparison failed", file=pfile, error=str(exc))

        # Sort and filter / Sắp xếp và lọc
        scores.sort(key=lambda x: x["confidence"], reverse=True)
        top = [s for s in scores[:top_n] if s["confidence"] / 100 >= min_confidence]

        return json.dumps({
            "chart_analyzed": chart_path,
            "patterns_checked": len(pattern_files),
            "top_matches": top,
            "best_pattern": top[0]["pattern"] if top else "None",
            "best_confidence": top[0]["confidence"] if top else 0.0,
        })


# ────────────────────────────────────────────────────────────────────────────
# Support / Resistance Tool
# ────────────────────────────────────────────────────────────────────────────

class _SRInput(BaseModel):
    symbol: str = Field(description="Currency pair symbol")
    timeframe: str = Field(description="Timeframe string")
    lookback: int = Field(default=100, description="Number of candles to analyse for S/R levels")
    tolerance_pips: float = Field(default=10.0, description="Pip tolerance for clustering S/R levels")


class SupportResistanceTool(BaseTool):
    """
    Detect key support and resistance levels from swing highs/lows.
    Phát hiện các mức hỗ trợ và kháng cự chính từ đỉnh/đáy swing.
    """

    name: str = "support_resistance"
    description: str = (
        "Detect key support and resistance price levels for a symbol using swing-high/low "
        "analysis over recent candles. Returns levels and whether the current price is near one."
    )
    args_schema: Type[BaseModel] = _SRInput

    def _run(
        self,
        symbol: str,
        timeframe: str,
        lookback: int = 100,
        tolerance_pips: float = 10.0,
    ) -> str:
        from utils.shared_state import shared_state

        df = shared_state.get_df(symbol, timeframe)
        if df is None or df.empty:
            return json.dumps({"error": "No data available", "levels": []})

        df = df.tail(lookback).reset_index(drop=True)
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        current_price = float(closes[-1])

        # Pip value / Giá trị pip
        pip = 0.0001 if "JPY" not in symbol else 0.01
        tol = tolerance_pips * pip

        # Swing highs (local maxima with window=3)
        # Đỉnh swing (cực đại cục bộ với cửa sổ=3)
        resistance_levels: List[float] = []
        support_levels: List[float] = []

        window = 3
        for i in range(window, len(df) - window):
            if all(highs[i] >= highs[i - j] for j in range(1, window + 1)) and \
               all(highs[i] >= highs[i + j] for j in range(1, window + 1)):
                resistance_levels.append(highs[i])

            if all(lows[i] <= lows[i - j] for j in range(1, window + 1)) and \
               all(lows[i] <= lows[i + j] for j in range(1, window + 1)):
                support_levels.append(lows[i])

        # Cluster levels within tolerance / Nhóm mức trong phạm vi dung sai
        resistance_levels = _cluster_levels(resistance_levels, tol)
        support_levels = _cluster_levels(support_levels, tol)

        # Check proximity of current price / Kiểm tra độ gần của giá hiện tại
        near_resistance = any(abs(current_price - r) <= tol for r in resistance_levels)
        near_support = any(abs(current_price - s) <= tol for s in support_levels)

        return json.dumps({
            "symbol": symbol,
            "timeframe": timeframe,
            "current_price": round(current_price, 5),
            "resistance_levels": [round(r, 5) for r in sorted(resistance_levels, reverse=True)[:5]],
            "support_levels": [round(s, 5) for s in sorted(support_levels, reverse=True)[:5]],
            "near_resistance": near_resistance,
            "near_support": near_support,
            "context": "at_resistance" if near_resistance else "at_support" if near_support else "mid_range",
        })


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers / Trợ giúp nội bộ
# ────────────────────────────────────────────────────────────────────────────

def _get_pattern_files(patterns_dir: str) -> List[str]:
    """Return list of PNG/JPG files in the patterns directory."""
    path = Path(patterns_dir)
    if not path.exists():
        return []
    return [str(f) for f in path.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg")]


def _load_gray(path: str) -> np.ndarray:
    """Load image as grayscale numpy array."""
    import cv2
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Cannot read image: {path}")
    return img


def _load_pil(path: str):
    """Load image as PIL Image."""
    from PIL import Image
    return Image.open(path).convert("RGB")


def _ssim_score(img1: np.ndarray, img2: np.ndarray) -> float:
    """
    Compute SSIM between two grayscale images after resizing to match.
    Tính SSIM giữa hai ảnh xám sau khi thay đổi kích thước để khớp.
    """
    import cv2
    from skimage.metrics import structural_similarity as ssim

    target_h, target_w = 256, 256
    img1_r = cv2.resize(img1, (target_w, target_h))
    img2_r = cv2.resize(img2, (target_w, target_h))

    score, _ = ssim(img1_r, img2_r, full=True)
    # SSIM can be negative; clamp to [0, 1]
    return float(max(0.0, score))


def _phash_score(img1, img2) -> float:
    """
    Compute normalised perceptual hash similarity in [0, 1].
    Tính tương đồng hash cảm nhận chuẩn hóa trong [0, 1].
    """
    import imagehash

    h1 = imagehash.phash(img1, hash_size=16)
    h2 = imagehash.phash(img2, hash_size=16)
    max_diff = len(h1.hash) ** 2  # 256 for hash_size=16
    hamming = h1 - h2
    return float(1.0 - hamming / max_diff)


# CLIP model is loaded once and cached / Model CLIP được tải một lần và lưu cache
_clip_model = None
_clip_processor = None


def _load_clip():
    global _clip_model, _clip_processor
    if _clip_model is None:
        try:
            from transformers import CLIPModel, CLIPProcessor

            _clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            _clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            _clip_model.eval()
            logger.info("CLIP model loaded successfully")
        except Exception as e:
            logger.warning("CLIP unavailable, skipping", error=str(e))
    return _clip_model, _clip_processor


def _clip_features(pil_img) -> Optional[np.ndarray]:
    """Extract normalised CLIP image feature vector."""
    import torch

    model, processor = _load_clip()
    if model is None or processor is None:
        return None

    try:
        with torch.no_grad():
            inputs = processor(images=pil_img, return_tensors="pt")
            feats = model.get_image_features(**inputs)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            return feats.cpu().numpy()[0]
    except Exception:
        return None


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity, already normalised → just dot product."""
    return float(np.clip(np.dot(a, b), 0.0, 1.0))


def _cluster_levels(levels: List[float], tolerance: float) -> List[float]:
    """
    Merge nearby price levels within tolerance into a single representative level.
    Gộp các mức giá gần nhau trong phạm vi dung sai thành một mức đại diện.
    """
    if not levels:
        return []
    levels = sorted(levels)
    clusters: List[List[float]] = []
    current_cluster = [levels[0]]

    for lvl in levels[1:]:
        if lvl - current_cluster[-1] <= tolerance:
            current_cluster.append(lvl)
        else:
            clusters.append(current_cluster)
            current_cluster = [lvl]
    clusters.append(current_cluster)

    return [float(np.mean(c)) for c in clusters]
