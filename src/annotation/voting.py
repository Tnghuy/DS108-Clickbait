"""Rubric-based voting logic for dual-model annotation ensemble.

Takes independent annotations from Qwen 2.5 3B and Gemma 2 2B,
applies direction-agreement logic, and produces a final label
with confidence score.

Rubric threshold: sum of 4 criteria scores (each 0-2), averaged across
both models. Total >= 4 -> clickbait, total <= 3 -> non-clickbait.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

CONFIDENCE_AGREE_BOOST = 0.10
CONFIDENCE_DISAGREE_PENALTY = 0.10


def calculate_rubric_vote(
    model_a_res: Dict[str, Any],
    model_b_res: Dict[str, Any],
    config: Dict[str, Any],  # noqa: unused — kept for API compat
) -> Tuple[int | None, str, float, int, int | None]:
    """Combine two model annotations into a single decision.

    Returns
    -------
    (label, status, confidence, rubric_total, severity)
    """
    if model_a_res.get("label") is None or model_b_res.get("label") is None:
        return None, "review", 0.5, -1, None

    a_scores = model_a_res.get("rubric_scores", [0, 0, 0, 0])
    b_scores = model_b_res.get("rubric_scores", [0, 0, 0, 0])
    a_total = sum(a_scores)
    b_total = sum(b_scores)
    rubric_total = round((a_total + b_total) / 2)

    sev_a = model_a_res.get("severity") or 0
    sev_b = model_b_res.get("severity") or 0
    severity = max(sev_a, sev_b)

    label_a = 1 if a_total >= 4 else 0
    label_b = 1 if b_total >= 4 else 0
    agree = (label_a == label_b)

    if rubric_total <= 3:
        rubric_label = 0
    else:
        rubric_label = 1

    # Confidence: always compute before status
    conf_a = model_a_res.get("confidence", 0.5)
    conf_b = model_b_res.get("confidence", 0.5)
    base_conf = (conf_a + conf_b) / 2.0
    if agree:
        confidence = base_conf + CONFIDENCE_AGREE_BOOST
    else:
        confidence = base_conf - CONFIDENCE_DISAGREE_PENALTY
    confidence = max(0.0, min(1.0, confidence))

    # Priority-based routing:
    # 1. Label disagreement (highest priority review)
    if not agree:
        status = "review"
    # 2. Label agreement but borderline scores on either model (3 or 4)
    elif a_total in [3, 4] or b_total in [3, 4]:
        status = "review"
    # 3. Agreement and clear non-borderline score
    else:
        status = "accepted"

    return rubric_label, status, confidence, rubric_total, severity
