"""Main annotation orchestrator — sequential dual-model ensemble pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml

from src.annotation.clients.qwen_client import QwenLocalClient
from src.annotation.clients.gemma_client import GemmaLocalClient
from src.annotation.voting import calculate_rubric_vote

logger = logging.getLogger(__name__)


class AnnotationEngine:
    def __init__(self, config_path="configs/annotation_config.yaml") -> None:
        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.input_file = self.project_root / self.config["paths"]["input_file"]
        self.output_accepted = self.project_root / self.config["paths"]["output_accepted"]
        self.output_review = self.project_root / self.config["paths"]["output_review"]

        qwen_path = self.project_root / self.config["paths"]["prompts"]["model_a"]
        gemma_path = self.project_root / self.config["paths"]["prompts"]["model_b"]
        with open(qwen_path, encoding="utf-8") as f:
            qwen_text = f.read()
        with open(gemma_path, encoding="utf-8") as f:
            gemma_text = f.read()

        ma = self.config["models"]["model_a"]
        mb = self.config["models"]["model_b"]
        self.model_a = QwenLocalClient(
            endpoint=ma["endpoint"],
            options={**ma["options"], "model_id": ma["id"], "system_prompt": qwen_text, "timeout": ma["options"].get("timeout", 20)},
        )
        self.model_b = GemmaLocalClient(
            endpoint=mb["endpoint"],
            options={**mb["options"], "model_id": mb["id"], "system_prompt": gemma_text, "timeout": mb["options"].get("timeout", 30)},
        )
        self.sampling_cfg = self.config.get("sampling", {})
        self.voting_cfg = self.config.get("voting", {})

    def _load_deduped_data(self):
        records = []
        with open(self.input_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def _sample_data(self, records):
        n = self.sampling_cfg.get("samples_per_source", 1000)
        seed = self.sampling_cfg.get("seed", 42)
        rng = random.Random(seed)
        by_source = {}
        for r in records:
            by_source.setdefault(r.get("source", "unknown"), []).append(r)
        sampled = []
        for src, items in sorted(by_source.items()):
            chosen = rng.sample(items, min(n, len(items)))
            sampled.extend(chosen)
            logger.info("Source %s: sampled %d/%d", src, len(chosen), len(items))

        return sampled

    def _get_processed_ids(self):
        processed = set()
        for out in (self.output_accepted, self.output_review):
            if out.exists():
                with open(out, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                processed.add(json.loads(line)["id"])
                            except (json.JSONDecodeError, KeyError):
                                pass
        return processed

    def _make_progress_bar(self, current: int, total: int, t_start: float, desc: str = "Progress") -> str:
        percent = (current / total) * 100 if total > 0 else 0
        elapsed = time.time() - t_start
        speed = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0
        
        def format_time(seconds: float) -> str:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            if h > 0:
                return f"{h:d}h{m:02d}m{s:02d}s"
            return f"{m:d}m{s:02d}s"
            
        bar_length = 20
        filled_length = int(round(bar_length * current / total)) if total > 0 else 0
        bar = "█" * filled_length + "░" * (bar_length - filled_length)
        
        return f"{desc}: |{bar}| {percent:.1f}% ({current}/{total}) | Speed: {speed:.1f} art/s | Elapsed: {format_time(elapsed)} | ETA: {format_time(eta)}"

    def run(self, resume=False):
        logger.info("=" * 60)
        logger.info("Annotation Engine starting (Phase-Sequential Concurrency)")
        logger.info("Model A: %s", self.model_a.model_id)
        logger.info("Model B: %s", self.model_b.model_id)
        self.model_a.health_check()
        self.model_b.health_check()

        records = self._load_deduped_data()
        sampled = self._sample_data(records)
        processed = self._get_processed_ids() if resume else set()
        remaining = [r for r in sampled if r["id"] not in processed]
        if not remaining:
            logger.info("All records already processed.")
            return

        self.output_accepted.parent.mkdir(parents=True, exist_ok=True)
        self.output_review.parent.mkdir(parents=True, exist_ok=True)

        t0 = time.time()

        # ── PHASE 1: Annotate with Model A in Parallel ────────────────────────
        logger.info("Starting Phase 1: Annotating with Model A (%s)...", self.model_a.model_id)
        
        cache_a_file = self.project_root / "data/annotated/cache_model_a.jsonl"
        res_a_dict = {}
        if resume and cache_a_file.exists():
            with open(cache_a_file, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        c_rec = json.loads(line)
                        res = c_rec["result"]
                        # Skip if result is failed or null so it gets retried
                        if res.get("label") is None or "Error:" in str(res.get("reason", "")):
                            continue
                        res_a_dict[c_rec["id"]] = res
            logger.info("Loaded %d valid cached annotations for Model A.", len(res_a_dict))

        remaining_a = [r for r in remaining if r["id"] not in res_a_dict]
        t_model_a = time.time()
        concurrency = self.config.get("concurrency", 1)
        
        if remaining_a:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {
                    executor.submit(self.model_a.annotate, r.get("title", ""), r.get("sapo", "")): r["id"]
                    for r in remaining_a
                }
                for idx, fut in enumerate(as_completed(futures), 1):
                    rid = futures[fut]
                    try:
                        res_a = fut.result()
                    except Exception as e:
                        logger.error("Model A failed for record %s: %s", rid, e)
                        res_a = {
                            "label": None, "confidence": 0.0, "rubric_scores": [0, 0, 0, 0],
                            "severity": None, "reason": f"Error: {e}", "thought_process": {}
                        }
                    res_a_dict[rid] = res_a
                    
                    # Write to cache immediately
                    cache_a_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(cache_a_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"id": rid, "result": res_a}, ensure_ascii=False) + "\n")
                        
                    total_processed = len(res_a_dict)
                    if idx % 10 == 0 or idx == len(remaining_a):
                        progress_msg = self._make_progress_bar(total_processed, len(remaining), t_model_a, "Model A Annotation Progress")
                        logger.info(progress_msg)
        else:
            logger.info("All records loaded from Model A cache. Skipping annotation.")

        logger.info("Completed Phase 1. Unloading Model A from VRAM...")
        self.model_a.unload()
        time.sleep(2)  # Allow GPU memory to settle

        # ── PHASE 2: Annotate with Model B in Parallel ────────────────────────
        logger.info("Starting Phase 2: Annotating with Model B (%s)...", self.model_b.model_id)
        
        cache_b_file = self.project_root / "data/annotated/cache_model_b.jsonl"
        res_b_dict = {}
        if resume and cache_b_file.exists():
            with open(cache_b_file, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        c_rec = json.loads(line)
                        res = c_rec["result"]
                        # Skip if result is failed or null so it gets retried
                        if res.get("label") is None or "Error:" in str(res.get("reason", "")):
                            continue
                        res_b_dict[c_rec["id"]] = res
            logger.info("Loaded %d valid cached annotations for Model B.", len(res_b_dict))

        remaining_b = [r for r in remaining if r["id"] not in res_b_dict]
        t_model_b = time.time()
        
        if remaining_b:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {
                    executor.submit(self.model_b.annotate, r.get("title", ""), r.get("sapo", "")): r["id"]
                    for r in remaining_b
                }
                for idx, fut in enumerate(as_completed(futures), 1):
                    rid = futures[fut]
                    try:
                        res_b = fut.result()
                    except Exception as e:
                        logger.error("Model B failed for record %s: %s", rid, e)
                        res_b = {
                            "label": None, "confidence": 0.0, "rubric_scores": [0, 0, 0, 0],
                            "severity": None, "reason": f"Error: {e}", "thought_process": {}
                        }
                    res_b_dict[rid] = res_b
                    
                    # Write to cache immediately
                    cache_b_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(cache_b_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"id": rid, "result": res_b}, ensure_ascii=False) + "\n")
                        
                    total_processed = len(res_b_dict)
                    if idx % 10 == 0 or idx == len(remaining_b):
                        progress_msg = self._make_progress_bar(total_processed, len(remaining), t_model_b, "Model B Annotation Progress")
                        logger.info(progress_msg)
        else:
            logger.info("All records loaded from Model B cache. Skipping annotation.")

        logger.info("Completed Phase 2. Unloading Model B from VRAM...")
        self.model_b.unload()

        # ── PHASE 3: Voting & 5% QA Sampling ───────────────────────────────────
        logger.info("Starting Phase 3: Ensemble Voting & QA Sampling...")
        
        accepted_records = []
        review_records = []

        for rec in remaining:
            rid = rec["id"]
            res_a = res_a_dict.get(rid, {})
            res_b = res_b_dict.get(rid, {})
            
            label, status, confidence, rubric_total, severity = calculate_rubric_vote(res_a, res_b, self.config)
            
            merged = {
                **rec,
                "model_a_label": res_a.get("label"),
                "model_a_confidence": res_a.get("confidence"),
                "model_a_rubric_scores": res_a.get("rubric_scores"),
                "model_a_severity": res_a.get("severity"),
                "model_a_reason": res_a.get("reason"),
                "model_a_thought_process": res_a.get("thought_process", {}),
                
                "model_b_label": res_b.get("label"),
                "model_b_confidence": res_b.get("confidence"),
                "model_b_rubric_scores": res_b.get("rubric_scores"),
                "model_b_severity": res_b.get("severity"),
                "model_b_reason": res_b.get("reason"),
                "model_b_thought_process": res_b.get("thought_process", {}),
                
                "rubric_total": rubric_total,
                "final_label": label,
                "severity": severity,
                "confidence": confidence,
                "status": status,
                "qa_sample": False  # default
            }

            if status == "accepted":
                accepted_records.append(merged)
            else:
                review_records.append(merged)

        # 5% QA Sampling from auto-accepted records
        qa_count = 0
        if accepted_records:
            k = max(1, int(len(accepted_records) * 0.05))
            seed = self.sampling_cfg.get("seed", 42)
            rng = random.Random(seed)
            qa_samples = rng.sample(accepted_records, k)
            
            for qa_rec in qa_samples:
                qa_rec["qa_sample"] = True
                qa_rec["status"] = "review"  # Route to human review queue
                qa_count += 1
                
            qa_ids = {r["id"] for r in qa_samples}
            accepted_records = [r for r in accepted_records if r["id"] not in qa_ids]
            review_records.extend(qa_samples)

        # Append to files
        logger.info("Writing output: accepted=%d records, review_queue=%d records (includes %d QA samples)",
                    len(accepted_records), len(review_records), qa_count)
        
        with open(self.output_accepted, "a", encoding="utf-8") as f:
            for r in accepted_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                
        with open(self.output_review, "a", encoding="utf-8") as f:
            for r in review_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        # Clean up cache files
        cache_a_file = self.project_root / "data/annotated/cache_model_a.jsonl"
        cache_b_file = self.project_root / "data/annotated/cache_model_b.jsonl"
        if cache_a_file.exists():
            cache_a_file.unlink()
        if cache_b_file.exists():
            cache_b_file.unlink()

        elapsed = time.time() - t0
        logger.info("Annotation Engine complete in %.1fs | accepted=%d review=%d (QA=%d)",
                    elapsed, len(accepted_records), len(review_records), qa_count)


def main():
    parser = argparse.ArgumentParser(description="Phase 5 Annotation Engine")
    parser.add_argument("--config", default="configs/annotation_config.yaml")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler("logs/annotation_engine.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    engine = AnnotationEngine(config_path=args.config)
    engine.run(resume=args.resume)


if __name__ == "__main__":
    main()
