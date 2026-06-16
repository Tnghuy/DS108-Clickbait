"""Gemma local annotation client via Ollama.

More nuanced reasoning annotator. Second model in the sequential pair.
VRAM note: ~3 GB with q4_K_M quantisation — runs after Qwen to fit 4 GB total.
Slower than Qwen 3B so default timeout is 30 s.
"""

from __future__ import annotations

import logging
from typing import Any

from .base_client import BaseClient

logger = logging.getLogger(__name__)


class GemmaLocalClient(BaseClient):
    """Ollama client for Gemma model."""

    model_id: str = "gemma2:2b-instruct-q4_K_M"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.default_timeout = self.options.get("timeout", 30)
