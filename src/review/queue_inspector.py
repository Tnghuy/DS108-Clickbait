"""Queue Inspector — load Phase 5 output, enrich với difficulty tier, review order.

Input:  data/annotated/human_review_queue.jsonl (Phase 5 output)
Output: data/review/enriched_queue.jsonl (Phase 6 input)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

import yaml

from src.review.schema import EnrichedRecord  # pyright: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


# ── Difficulty tier logic ──────────────────────────────────────────────────


def classify_difficulty(record: Dict[str, Any]) -> str:
    """Phân loại record thành easy / medium / hard dựa trên LLM outputs.

    Logic:
    - easy:   models đồng ý label + cả 2 confidences >= 0.7
    - hard:   cả 2 confidences < 0.5 HOẶC rubric_total = 4 (borderline)
    - medium: còn lại (models disagree ở confidence 0.5-0.7)
    """
    label_a = record.get("model_a_label")
    label_b = record.get("model_b_label")
    conf_a = record.get("model_a_confidence", 0.0)
    conf_b = record.get("model_b_confidence", 0.0)
    rubric_total = record.get("rubric_total", 0)

    if label_a is None or label_b is None:
        return "hard"

    models_agree = label_a == label_b
    both_high_conf = conf_a >= 0.7 and conf_b >= 0.7
    both_low_conf = conf_a < 0.5 and conf_b < 0.5
    is_borderline = rubric_total == 4

    if models_agree and both_high_conf and not is_borderline:
        return "easy"
    elif both_low_conf or is_borderline:
        return "hard"
    else:
        return "medium"


# ── Main inspector ─────────────────────────────────────────────────────────


class QueueInspector:
    """Load + enrich Phase 5 output."""

    def __init__(self, config_path: str = "configs/review_config.yaml") -> None:
        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.input_path = self.project_root / self.config["paths"]["input_queue"]
        self.output_path = self.project_root / self.config["paths"]["enriched_queue"]

        self.total_records = 0
        self.easy_count = 0
        self.medium_count = 0
        self.hard_count = 0

    def load_phase5_output(self) -> list[dict]:
        """Đọc human_review_queue.jsonl từ Phase 5, skipping malformed records without title."""
        records: list[dict] = []
        skipped_count = 0
        with open(self.input_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    if not rec.get("title"):
                        skipped_count += 1
                        continue
                    records.append(rec)
        if skipped_count > 0:
            logger.warning("Skipped %d records due to missing or null title.", skipped_count)
        logger.info("Loaded %d records from %s", len(records), self.input_path)
        return records

    def enrich_record(self, record: dict, index: int) -> EnrichedRecord:
        """Enrich 1 Phase 5 record với Phase 6 fields."""
        difficulty = classify_difficulty(record)

        enriched = EnrichedRecord(
            # Phase 5 fields
            id=record["id"],
            source=record.get("source", ""),
            url=record.get("url", ""),
            title=record.get("title", ""),
            sapo=record.get("sapo"),
            publish_date=record.get("publish_date"),
            body_preview=record.get("body_preview"),
            quality_score=record.get("quality_score"),
            model_a_label=record.get("model_a_label"),
            model_a_confidence=record.get("model_a_confidence"),
            model_a_rubric_scores=record.get("model_a_rubric_scores"),
            model_a_severity=record.get("model_a_severity"),
            model_a_reason=record.get("model_a_reason"),
            model_b_label=record.get("model_b_label"),
            model_b_confidence=record.get("model_b_confidence"),
            model_b_rubric_scores=record.get("model_b_rubric_scores"),
            model_b_severity=record.get("model_b_severity"),
            model_b_reason=record.get("model_b_reason"),
            rubric_total=record.get("rubric_total"),
            final_label=record.get("final_label"),
            severity=record.get("severity"),
            confidence=record.get("confidence"),
            # Phase 6 enrichments
            difficulty_tier=difficulty,  # type: ignore[arg-type]
            review_status="pending",
            review_order=index,
        )

        if difficulty == "easy":
            self.easy_count += 1
        elif difficulty == "medium":
            self.medium_count += 1
        else:
            self.hard_count += 1

        return enriched

    def run(self) -> list[EnrichedRecord]:
        """Run full pipeline: load -> enrich -> write -> return."""
        logger.info("=" * 60)
        logger.info("Queue Inspector — Phase 6A")
        logger.info("=" * 60)

        raw_records = self.load_phase5_output()
        self.total_records = len(raw_records)

        if self.total_records == 0:
            logger.warning("Input queue is empty! Nothing to review.")
            return []

        enriched: list[EnrichedRecord] = []
        for idx, record in enumerate(raw_records):
            enriched.append(self.enrich_record(record, idx))

        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.output_path, "w", encoding="utf-8") as f:
            for record in enriched:
                f.write(record.model_dump_json(ensure_ascii=False) + "\n")

        logger.info("Enriched %d records -> %s", self.total_records, self.output_path)
        logger.info(
            "Difficulty breakdown: easy=%d, medium=%d, hard=%d",
            self.easy_count,
            self.medium_count,
            self.hard_count,
        )
        logger.info(
            "Percentages: easy=%.1f%%, medium=%.1f%%, hard=%.1f%%",
            100 * self.easy_count / self.total_records,
            100 * self.medium_count / self.total_records,
            100 * self.hard_count / self.total_records,
        )

        return enriched


# ── CLI entry point ────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Phase 6A: Queue Inspector")
    parser.add_argument(
        "--config",
        default="configs/review_config.yaml",
        help="Path to review config YAML",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    inspector = QueueInspector(config_path=args.config)
    enriched = inspector.run()

    if enriched:
        print(f"\n{'=' * 60}")
        print(f"Queue Inspector — Summary")
        print(f"{'=' * 60}")
        print(f"Total records: {inspector.total_records}")
        print(
            f"  Easy:   {inspector.easy_count:>5} "
            f"({100 * inspector.easy_count / inspector.total_records:.1f}%)"
        )
        print(
            f"  Medium: {inspector.medium_count:>5} "
            f"({100 * inspector.medium_count / inspector.total_records:.1f}%)"
        )
        print(
            f"  Hard:   {inspector.hard_count:>5} "
            f"({100 * inspector.hard_count / inspector.total_records:.1f}%)"
        )
        print(f"Output: {inspector.output_path}")
        print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
