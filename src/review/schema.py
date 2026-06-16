"""Pydantic schemas cho Human Review Queue — Phase 6."""

from __future__ import annotations

from enum import IntEnum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────


class DifficultyTier(IntEnum):
    EASY = 1
    MEDIUM = 2
    HARD = 3


class ReviewStatus(IntEnum):
    PENDING = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    SKIPPED = 3


# ── Input: Phase 5 output (giữ nguyên field names) ────────────────────────


class Phase5Output(BaseModel):
    """Schema cho record từ Phase 5 (final_annotated.jsonl / human_review_queue.jsonl)."""

    id: str
    source: str
    url: str
    title: str
    sapo: str
    publish_date: Optional[Union[str, int]] = None
    crawl_timestamp: Optional[str] = None
    crawl_method: Optional[str] = None
    rss_feed: Optional[str] = None
    source_category: Optional[str] = None
    feed_type: Optional[str] = None
    body_text: Optional[str] = None
    body_preview: Optional[str] = None
    extraction_success: Optional[bool] = None
    quality_score: Optional[int] = None
    quality_breakdown: Optional[dict] = None

    # Phase 5 LLM outputs (model_a = Qwen, model_b = Gemma)
    model_a_label: Optional[int] = None
    model_a_confidence: Optional[float] = None
    model_a_rubric_scores: Optional[List[int]] = None
    model_a_severity: Optional[int] = None
    model_a_reason: Optional[str] = None
    model_b_label: Optional[int] = None
    model_b_confidence: Optional[float] = None
    model_b_rubric_scores: Optional[List[int]] = None
    model_b_severity: Optional[int] = None
    model_b_reason: Optional[str] = None

    # Aggregated Phase 5 output
    rubric_total: Optional[int] = None
    final_label: Optional[int] = None
    severity: Optional[int] = None
    confidence: Optional[float] = None
    status: Optional[str] = None


# ── Output: enriched record cho Phase 6 ───────────────────────────────────


class ReviewDecision(BaseModel):
    """Human review decision cho 1 record."""

    record_id: str = Field(..., description="ID của headline được review")
    reviewer_id: str = Field(..., description="ID của reviewer")
    human_label: int = Field(..., description="0=non-clickbait, 1=clickbait")
    human_rubric_scores: List[int] = Field(
        ..., min_length=4, max_length=4, description="[C1, C2, C3, C4] mỗi score 0-2"
    )
    human_severity: int = Field(..., ge=0, le=3, description="0-3")
    human_notes: Optional[str] = Field(None, description="Ghi chú tuỳ chọn")
    review_timestamp: str = Field(..., description="ISO timestamp khi review")
    duration_seconds: Optional[float] = Field(
        None, description="Thời gian reviewer mất để quyết định"
    )


class EnrichedRecord(BaseModel):
    """Record sau khi được enrich bởi queue_inspector."""

    # ── Phase 5 fields (giữ nguyên) ──
    id: str
    source: str
    url: str
    title: str
    sapo: Optional[str] = None
    publish_date: Optional[Union[str, int]] = None
    body_preview: Optional[str] = None
    quality_score: Optional[int] = None

    # Phase 5 model outputs
    model_a_label: Optional[int] = None
    model_a_confidence: Optional[float] = None
    model_a_rubric_scores: Optional[List[int]] = None
    model_a_severity: Optional[int] = None
    model_a_reason: Optional[str] = None
    model_b_label: Optional[int] = None
    model_b_confidence: Optional[float] = None
    model_b_rubric_scores: Optional[List[int]] = None
    model_b_severity: Optional[int] = None
    model_b_reason: Optional[str] = None

    rubric_total: Optional[int] = None
    final_label: Optional[int] = None
    severity: Optional[int] = None
    confidence: Optional[float] = None

    # ── Phase 6 enrichments ──
    difficulty_tier: Literal["easy", "medium", "hard"] = Field(
        ..., description="Độ khó dựa trên model disagreement + confidence"
    )
    review_status: Literal["pending", "in_progress", "completed", "skipped"] = "pending"
    review_order: int = Field(..., description="Thứ tự review (0-indexed)")
    review_progress: str = Field(
        default="", description="VD: '3/1259' — cập nhật runtime"
    )

    # ── Human decision (mặc định None, được điền sau khi review) ──
    human_label: Optional[int] = None
    human_rubric_scores: Optional[List[int]] = Field(None, min_length=4, max_length=4)
    human_severity: Optional[int] = None
    human_notes: Optional[str] = None
    human_verified: bool = False
    review_timestamp: Optional[str] = None


# ── Session tracking ───────────────────────────────────────────────────────


class SessionCheckpoint(BaseModel):
    """Checkpoint để resume sau khi crash / quit giữa chừng."""

    reviewer_id: str
    started_at: str
    last_updated: str
    total_records: int
    completed_count: int
    skipped_count: int
    current_index: int  # next record to review
    completed_ids: List[str] = Field(default_factory=list)
    skipped_ids: List[str] = Field(default_factory=list)
    decisions: List[ReviewDecision] = Field(default_factory=list)


class SessionLogEntry(BaseModel):
    """1 entry trong session_log.jsonl."""

    reviewer_id: str
    event: Literal["start", "checkpoint", "resume", "quit", "complete"]
    timestamp: str
    total_records: int
    completed_count: int
    skipped_count: int
    notes: Optional[str] = None


class HumanLLMAgreement(BaseModel):
    """Metrics: agreement giữa human decision và Phase 5 prediction."""

    total_compared: int = 0
    label_agree: int = 0
    label_disagree: int = 0
    severity_agree: int = 0
    severity_disagree: int = 0
    # Per severity breakdown
    severity_0_count: int = 0
    severity_1_count: int = 0
    severity_2_count: int = 0
    severity_3_count: int = 0
    # Confidence correlation (for records where LLM agreed with human)
    avg_confidence_when_correct: Optional[float] = None
    avg_confidence_when_wrong: Optional[float] = None

    @property
    def label_agreement_rate(self) -> float:
        if self.total_compared == 0:
            return 0.0
        return self.label_agree / self.total_compared

    @property
    def severity_agreement_rate(self) -> float:
        if self.total_compared == 0:
            return 0.0
        return self.severity_agree / self.total_compared
