"""Session Manager — checkpoint + resume + session logging cho Human Review.

Input: data/review/session_checkpoint.json (checkpoint file)
Output: data/review/session_log.jsonl (log mỗi session event)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from src.review.schema import (  # pyright: ignore[reportMissingImports]
    ReviewDecision,
    SessionCheckpoint,
    SessionLogEntry,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """Quản lý reviewer session: checkpoint, resume, logging."""

    def __init__(self, config_path: str = "configs/review_config.yaml") -> None:
        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.reviewer_id = self.config["reviewer"]["id"]
        self.checkpoint_interval = self.config["review"]["checkpoint_interval"]

        self.checkpoint_path = (
            self.project_root / self.config["paths"]["session_checkpoint"]
        )
        self.log_path = self.project_root / self.config["paths"]["session_log"]

    def create_checkpoint(
        self,
        current_index: int,
        total_records: int,
        completed_ids: list[str],
        skipped_ids: list[str],
        decisions: list[ReviewDecision],
    ) -> SessionCheckpoint:
        """Tạo checkpoint mới."""
        now = datetime.now(timezone.utc).isoformat()
        checkpoint = SessionCheckpoint(
            reviewer_id=self.reviewer_id,
            started_at=now,
            last_updated=now,
            total_records=total_records,
            completed_count=len(completed_ids),
            skipped_count=len(skipped_ids),
            current_index=current_index,
            completed_ids=completed_ids,
            skipped_ids=skipped_ids,
            decisions=decisions,
        )

        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.checkpoint_path, "w", encoding="utf-8") as f:
            f.write(checkpoint.model_dump_json(ensure_ascii=False) + "\n")

        logger.debug(
            "Checkpoint saved: %d/%d completed",
            len(completed_ids),
            total_records,
        )
        return checkpoint

    def load_checkpoint(self) -> Optional[SessionCheckpoint]:
        """Load checkpoint cũ nếu có, None nếu chưa có."""
        if not self.checkpoint_path.exists():
            return None

        with open(self.checkpoint_path, encoding="utf-8") as f:
            data = json.loads(f.read())

        return SessionCheckpoint(**data)

    def should_checkpoint(self, completed_count: int) -> bool:
        """Kiểm tra có cần lưu checkpoint không (mỗi N records)."""
        return completed_count > 0 and completed_count % self.checkpoint_interval == 0

    def log_event(
        self,
        event: str,
        total_records: int,
        completed_count: int,
        skipped_count: int,
        notes: Optional[str] = None,
    ) -> None:
        """Ghi 1 session log entry."""
        now = datetime.now(timezone.utc).isoformat()
        log_entry = SessionLogEntry(
            reviewer_id=self.reviewer_id,
            event=event,
            timestamp=now,
            total_records=total_records,
            completed_count=completed_count,
            skipped_count=skipped_count,
            notes=notes,
        )

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(log_entry.model_dump_json(ensure_ascii=False) + "\n")

        logger.info("Session log: %s — %s", event, notes or "")
