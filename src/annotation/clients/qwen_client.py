"""Qwen local annotation client via Ollama.

Fast, conservative annotator. First model in the sequential pair.
VRAM note: ~2.5 GB with q4_K_M quantisation on RTX 3050 Ti.
"""

from __future__ import annotations

import logging
from typing import Any

from .base_client import BaseClient

logger = logging.getLogger(__name__)


class QwenLocalClient(BaseClient):
    """Ollama client for Qwen model."""

    model_id: str = "qwen2.5:3b-instruct-q4_K_M"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.default_timeout = self.options.get("timeout", 20)
