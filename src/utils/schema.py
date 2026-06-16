"""Pydantic schemas for data integrity and validation at each pipeline phase."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, ValidationError


# ── Phase 1: Raw Crawled Record ───────────────────────────────────────────

class RawRecord(BaseModel):
    """Schema for raw crawled articles from RSS/Sitemaps (data/raw/)."""
    id: str = Field(..., description="Unique record identifier format: <source>_<md5>")
    source: str = Field(..., description="Publisher source identifier")
    url: str = Field(..., description="Normalized article URL")
    title: Optional[str] = Field(None, description="Article headline (optional in raw sitemaps)")
    sapo: Optional[str] = Field(None, description="Article summary / lead paragraph")
    publish_date: Optional[Union[str, int]] = Field(None, description="ISO timestamp or unix timestamp")
    crawl_timestamp: str = Field(..., description="ISO timestamp of crawl time")
    crawl_method: Literal["rss", "sitemap"] = Field(..., description="Discovery method")
    rss_feed: Optional[str] = Field(None, description="Feed URL if RSS crawled")
    feed_type: Optional[str] = Field(None, description="Category of the RSS feed")
    source_category: str = Field(..., description="E.g., mainstream or entertainment")


# ── Phase 2: Extracted Content Record ─────────────────────────────────────

class FilteredRecord(RawRecord):
    """Schema for articles after HTML text extraction (data/filtered/)."""
    title: str = Field(..., description="Article headline (required after extraction)")
    body_text: str = Field(..., min_length=150, description="Cleaned full article body text")
    body_preview: str = Field(..., max_length=510, description="Truncated preview of the body")
    extraction_success: bool = Field(True, description="Indicates if parsing succeeded")


# ── Phase 3: Heuristic Quality Validated Record ───────────────────────────

class ValidatedRecord(FilteredRecord):
    """Schema for articles after heuristic quality scoring (data/validated/)."""
    quality_score: int = Field(..., ge=0, le=6, description="Sum of 6 quality checks")
    quality_breakdown: Dict[str, bool] = Field(..., description="Details of individual quality check flags")


# ── Phase 4 & 5: Deduplicated Record ──────────────────────────────────────

class DeduplicatedRecord(ValidatedRecord):
    """Schema for articles after exact and semantic deduplication (data/dedup/)."""
    # Inherits all validated fields. Schema is identical but guarantees uniqueness.
    pass


# ── Phase 9: Final Dataset Record ─────────────────────────────────────────

class FinalRecord(DeduplicatedRecord):
    """Schema for finalized articles with splits, voting labels and review state (data/final/)."""
    model_a_label: Optional[int] = Field(None, ge=0, le=1)
    model_a_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    model_a_rubric_scores: Optional[List[int]] = Field(None, min_length=4, max_length=4)
    model_a_severity: Optional[int] = Field(None, ge=0, le=3)
    model_a_reason: Optional[str] = None
    model_a_thought_process: Optional[dict] = None

    model_b_label: Optional[int] = Field(None, ge=0, le=1)
    model_b_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    model_b_rubric_scores: Optional[List[int]] = Field(None, min_length=4, max_length=4)
    model_b_severity: Optional[int] = Field(None, ge=0, le=3)
    model_b_reason: Optional[str] = None
    model_b_thought_process: Optional[dict] = None

    rubric_total: Optional[int] = Field(None, ge=0, le=8)
    final_label: float = Field(..., ge=0.0, le=1.0, description="0.0 or 1.0 clickbait classification")
    severity: float = Field(..., ge=0.0, le=3.0, description="Max severity score 0.0-3.0")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Weighted annotation confidence")
    status: Literal["accepted", "review"] = Field(..., description="Auto-accepted or routed to human review")
    human_verified: bool = Field(False, description="True if verified by human review")
    split: Literal["train", "validation", "test"] = Field(..., description="Dataset split assignment")


# ── Validation Helper ─────────────────────────────────────────────────────

def validate_record(record: dict, schema_cls: type[BaseModel]) -> bool:
    """
    Validate a record dictionary against a Pydantic schema class.
    Logs warnings on validation failure.
    """
    try:
        schema_cls.model_validate(record)
        return True
    except ValidationError as e:
        import logging
        logging.getLogger(__name__).warning(
            "Schema validation failed for record %s against %s. Errors: %s",
            record.get("id", "unknown"),
            schema_cls.__name__,
            e.errors()
        )
        return False
