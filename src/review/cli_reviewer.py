from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from src.review.schema import (  # pyright: ignore[reportMissingImports]
    EnrichedRecord,
    ReviewDecision,
)
from src.review.keyboard_handler import (
    confirm_action,
    prompt_label,
    prompt_rubric_score,
    prompt_severity,
)
from src.review.session_manager import SessionManager
from src.review.ui_components import (
    render_completion_message,
    render_headline,
    render_help,
    render_header,
    render_label_prompt,
    render_model_outputs,
    render_progress,
    render_rubric_prompt,
    render_shortcuts,
)

logger = logging.getLogger(__name__)


class CLIReviewer:
    def __init__(self, config_path: str = "configs/review_config.yaml", blind: bool = False) -> None:
        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.reviewer_id = self.config["reviewer"]["id"]
        self.blind = blind
        self.session_mgr = SessionManager(config_path)
        self.decisions: list[ReviewDecision] = []
        self.completed_ids: list[str] = []
        self.skipped_ids: list[str] = []
        self.start_time: Optional[float] = None
        
        # Load rubric criteria dynamically from configuration
        self.criteria = []
        for crit in self.config["rubric"]["criteria"]:
            self.criteria.append((crit["id"], crit["name"]))

    def _load_enriched_queue(self) -> list[EnrichedRecord]:
        qp = self.project_root / self.config["paths"]["enriched_queue"]
        
        # Automatically run QueueInspector if the queue file is missing
        if not qp.exists():
            logger.info("Enriched queue file not found. Running QueueInspector automatically...")
            from src.review.queue_inspector import QueueInspector
            inspector = QueueInspector(config_path=str(self.project_root / "configs/review_config.yaml"))
            inspector.run()
            
        records: list[EnrichedRecord] = []
        with open(qp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(EnrichedRecord.model_validate_json(line))
        logger.info("Loaded %d records", len(records))
        return records

    def _save_decision(self, d: ReviewDecision) -> None:
        dp = self.project_root / self.config["paths"]["decisions"]
        dp.parent.mkdir(parents=True, exist_ok=True)
        with open(dp, "a", encoding="utf-8") as f:
            f.write(d.model_dump_json(ensure_ascii=False) + "\n")

    def _review_single(self, record: EnrichedRecord, idx: int, total: int) -> bool:
        t0 = time.time()
        render_header(self.reviewer_id, 0, idx, total, record.difficulty_tier)
        
        # Publisher Bias Mitigation: hide source and url
        render_headline(record.title, "[ẨN DANH]", "[ẨN DANH]")
        
        if record.sapo:
            from src.review.ui_components import render_sapo
            render_sapo(record.sapo)
        
        if not self.blind:
            render_model_outputs(record.model_dump())
        else:
            from rich.console import Console
            Console().print("[dim][Chế độ Blind Test: Kết quả dự đoán của LLM đã bị ẩn để đảm bảo tính khách quan][/dim]")

        render_rubric_prompt()
        scores: list[int] = []
        for cid, cname in self.criteria:
            scores.append(prompt_rubric_score(cid, cname))

        rubric_total = sum(scores)
        auto_label = 1 if rubric_total >= 4 else 0

        render_label_prompt()
        human_label = prompt_label()
        human_severity = prompt_severity()

        if record.difficulty_tier != "easy" and human_label != auto_label:
            msg = (
                f"Ban chon label={human_label} (0=non-CB, 1=CB) "
                f"nhung rubric_total={rubric_total} -> auto={auto_label}. "
                f"Xac nhan?"
            )
            if not confirm_action(msg):
                return self._review_single(record, idx, total)

        dur = round(time.time() - t0, 2)
        decision = ReviewDecision(
            record_id=record.id,
            reviewer_id=self.reviewer_id,
            human_label=human_label,
            human_rubric_scores=scores,
            human_severity=human_severity,
            review_timestamp=datetime.now(timezone.utc).isoformat(),
            duration_seconds=dur,
        )
        self._save_decision(decision)
        self.decisions.append(decision)
        self.completed_ids.append(record.id)
        return True

    def run(self, resume: bool = False) -> None:
        self.start_time = time.time()
        records = self._load_enriched_queue()
        total = len(records)
        if total == 0:
            logger.warning("Queue empty! Nothing to review.")
            return

        start_idx = 0
        if resume:
            ckpt = self.session_mgr.load_checkpoint()
            if ckpt:
                start_idx = ckpt.current_index
                self.completed_ids = ckpt.completed_ids[:]
                self.skipped_ids = ckpt.skipped_ids[:]
                self.decisions = ckpt.decisions[:]
                logger.info("Resumed: %d/%d", len(self.completed_ids), total)

        self.session_mgr.log_event(
            "start", total, len(self.completed_ids), len(self.skipped_ids)
        )

        try:
            for i in range(start_idx, total):
                rec = records[i]
                if rec.id in self.completed_ids:
                    continue
                render_progress(
                    len(self.completed_ids), total, len(self.skipped_ids)
                )
                ok = self._review_single(rec, i, total)
                if ok:
                    logger.info(
                        "[%d/%d] %s -> label=%d",
                        i + 1,
                        total,
                        rec.id[:12],
                        self.decisions[-1].human_label,
                    )
                if self.session_mgr.should_checkpoint(len(self.completed_ids)):
                    self.session_mgr.create_checkpoint(
                        i + 1,
                        total,
                        self.completed_ids,
                        self.skipped_ids,
                        self.decisions,
                    )
                    self.session_mgr.log_event(
                        "checkpoint",
                        total,
                        len(self.completed_ids),
                        len(self.skipped_ids),
                    )
        except KeyboardInterrupt:
            logger.info("Interrupted - saving...")
        finally:
            self.session_mgr.create_checkpoint(
                total,
                total,
                self.completed_ids,
                self.skipped_ids,
                self.decisions,
            )
            evt = "quit" if len(self.completed_ids) < total else "complete"
            self.session_mgr.log_event(
                evt, total, len(self.completed_ids), len(self.skipped_ids)
            )
            elapsed = time.time() - (self.start_time or time.time())
            render_completion_message(
                {
                    "completed": len(self.completed_ids),
                    "skipped": len(self.skipped_ids),
                    "total_time": elapsed,
                    "output_path": str(
                        self.project_root / self.config["paths"]["decisions"]
                    ),
                }
            )


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Phase 6: Human Review CLI")
    p.add_argument("--reviewer", default="huy")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--config", default="configs/review_config.yaml")
    p.add_argument("--blind", action="store_true", help="Hide LLM predictions (Double-blind annotation)")
    a = p.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    r = CLIReviewer(config_path=a.config, blind=a.blind)
    r.run(resume=a.resume)


if __name__ == "__main__":
    main()
