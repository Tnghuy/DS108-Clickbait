"""Feature Engineering - Phase 7 (spec s67).

Extracts features for EDA visualizations from annotated dataset.
Handles: date conversion, label mapping, confidence bucketing,
text statistics, rubric analysis, agreement flags.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def load_annotated(path: str) -> pd.DataFrame:
    """Load annotated JSONL into DataFrame."""
    import json

    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    df = pd.DataFrame(records)
    logger.info("Loaded %d records, %d columns", len(df), len(df.columns))
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add all engineered features to DataFrame."""
    df = df.copy()

    # --- Date conversion -------------------------------------------------------
    df = _convert_dates(df)

    # --- Label mapping ---------------------------------------------------------
    df = _map_labels(df)

    # --- Confidence bucketing --------------------------------------------------
    df = _bucket_confidence(df)

    # --- Text statistics -------------------------------------------------------
    df = _text_stats(df)

    # --- Rubric analysis -------------------------------------------------------
    df = _rubric_features(df)

    # --- Agreement flags -------------------------------------------------------
    df = _agreement_flags(df)

    # --- Source category mapping -----------------------------------------------
    df = _source_categories(df)

    return df


def _convert_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convert publish_date and crawl_timestamp to datetime."""
    if "publish_date" in df.columns:
        raw = df["publish_date"]
        if pd.api.types.is_numeric_dtype(raw):
            # Unix epoch seconds
            df["publish_date_dt"] = pd.to_datetime(raw, unit="s", errors="coerce")
        else:
            df["publish_date_dt"] = pd.to_datetime(raw, errors="coerce")
        df["publish_year"] = df["publish_date_dt"].dt.year
        df["publish_month"] = df["publish_date_dt"].dt.month
        df["publish_dow"] = df["publish_date_dt"].dt.dayofweek  # 0=Mon

    if "crawl_timestamp" in df.columns:
        df["crawl_date_dt"] = pd.to_datetime(df["crawl_timestamp"], errors="coerce")
    df["crawl_date"] = df["crawl_date_dt"].dt.date
    return df


def _map_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Create human-readable label columns."""
    if "final_label" in df.columns:
        df["label_name"] = df["final_label"].map({1: "clickbait", 0: "non_clickbait"})
    if "model_a_label" in df.columns:
        df["model_a_name"] = df["model_a_label"].map({1: "clickbait", 0: "non_clickbait"})
    if "model_b_label" in df.columns:
        df["model_b_name"] = df["model_b_label"].map({1: "clickbait", 0: "non_clickbait"})
    return df


def _bucket_confidence(df: pd.DataFrame) -> pd.DataFrame:
    """Create confidence level buckets."""
    if "confidence" in df.columns:
        bins = [0.0, 0.60, 0.75, 0.90, 1.01]
        labels = ["low", "medium", "high", "very_high"]
        df["confidence_level"] = pd.cut(
            df["confidence"], bins=bins, labels=labels, include_lowest=True
        ).astype(str)
        df["confidence_level"] = df["confidence_level"].replace("nan", "unknown")
    return df


def _text_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute text length statistics and linguistic markers."""
    import re
    for col in ("title", "sapo", "body_preview"):
        if col in df.columns:
            df[f"{col}_len"] = df[col].astype(str).str.len()
            df[f"{col}_word_count"] = df[col].astype(str).str.split().str.len()

    if "title" in df.columns:
        titles_str = df["title"].astype(str).str.lower()
        df["title_has_qmark"] = titles_str.str.contains(r"\?", regex=True)
        df["title_has_excl"] = titles_str.str.contains(r"!", regex=False)
        df["title_has_ellipsis"] = titles_str.str.contains(r"\.\.\.", regex=True)
        
        clickbait_keywords = [
            "sốc", "ngã ngửa", "nóng", "cực hot", "không thể tin nổi", 
            "bí mật", "hé lộ", "sự thật", "xôn xao", "chấn động", 
            "lộ diện", "bất ngờ", "đằng sau", "chi tiết", "cận cảnh", "ngỡ ngàng", "kinh hoàng"
        ]
        # Count keywords using word boundaries where possible or direct search
        pattern = "|".join(re.escape(kw) for kw in clickbait_keywords)
        df["title_sensational_count"] = titles_str.apply(lambda x: len(re.findall(pattern, x)))
        
    return df


def _rubric_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract rubric score features."""
    for prefix in ("model_a", "model_b"):
        col = f"{prefix}_rubric_scores"
        if col in df.columns:
            scores = df[col].apply(lambda x: _safe_list(x))
            df[f"{prefix}_rubric_total"] = scores.apply(lambda s: sum(s) if s else None)
            for i, name in enumerate(["C1_info_hiding", "C2_emotional", "C3_misleading", "C4_urgency"]):
                df[f"{prefix}_{name}"] = scores.apply(lambda s, idx=i: s[idx] if s and idx < len(s) else None)
    return df


def _safe_list(val: Any) -> list[int]:
    """Safely convert to list of ints."""
    if isinstance(val, list):
        return [int(x) for x in val]
    if isinstance(val, str):
        try:
            import ast
            parsed = ast.literal_eval(val)
            return [int(x) for x in parsed]
        except Exception:
            return []
    return []


def _agreement_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Flag agreements/disagreements between models."""
    if "model_a_label" in df.columns and "model_b_label" in df.columns:
        mask = df["model_a_label"].notna() & df["model_b_label"].notna()
        a = df.loc[mask, "model_a_label"]
        b = df.loc[mask, "model_b_label"]
        df["models_agree"] = False
        df.loc[mask, "models_agree"] = (a == b).values
        df["disagreement_severity"] = df.get("model_a_severity", 0) - df.get("model_b_severity", 0)
    return df


def _source_categories(df: pd.DataFrame) -> pd.DataFrame:
    """Map sources to categories."""
    category_map = {
        "tuoitre": "mainstream",
        "nhandan": "mainstream",
        "thanhnien": "mainstream",
        "kenh14": "entertainment",
        "soha": "mainstream",
        "afamily": "entertainment",
    }
    if "source" in df.columns:
        df["source_category"] = df["source"].map(category_map).fillna("other")
    return df


def get_feature_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Generate summary statistics for all features."""
    summary: dict[str, Any] = {}

    if "final_label" in df.columns:
        summary["class_distribution"] = df["final_label"].value_counts().to_dict()
        summary["class_balance"] = df["final_label"].value_counts(normalize=True).round(4).to_dict()

    if "source" in df.columns:
        summary["source_distribution"] = df["source"].value_counts().to_dict()

    if "confidence" in df.columns:
        summary["confidence_stats"] = {
            "mean": round(df["confidence"].mean(), 4),
            "std": round(df["confidence"].std(), 4),
            "min": round(df["confidence"].min(), 4),
            "max": round(df["confidence"].max(), 4),
        }

    if "status" in df.columns:
        summary["status_distribution"] = df["status"].value_counts().to_dict()

    return summary
