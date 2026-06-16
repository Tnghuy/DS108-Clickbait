"""
Deduplication package for Vietnamese clickbait dataset.

Provides exact and semantic deduplication capabilities:
- Exact deduplication via normalized URL/title comparison
- Semantic deduplication via sentence-transformer embeddings
- Configurable similarity thresholds for duplicate detection
"""

from .exact_dedup import ExactDeduplicator
from .semantic_dedup import SemanticDeduplicator

__all__ = ["ExactDeduplicator", "SemanticDeduplicator"]
