#!/usr/bin/env python3
"""
Vietnamese Clickbait Dataset Pipeline Orchestrator (main.py)

Allows running the entire data pipeline (Phase 1 to Phase 9) sequentially,
or executing specific steps selectively.
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("PipelineOrchestrator")

STEPS = {
    1: {"name": "RSS/Sitemap Crawling", "cmd": [sys.executable, "-m", "src.scraping.crawler_wrapper"]},
    2: {"name": "Article Text Extraction", "cmd": [sys.executable, "-m", "src.scraping.extractor"]},
    3: {"name": "Quality Validation Scoring", "cmd": [sys.executable, "-m", "src.validation.quality_scorer"]},
    4: {"name": "Exact Deduplication", "cmd": [sys.executable, "-m", "src.dedup.exact_dedup"]},
    5: {"name": "Semantic Deduplication", "cmd": [sys.executable, "-m", "src.dedup.semantic_dedup"]},
    6: {"name": "Ensemble LLM Annotation", "cmd": [sys.executable, "-m", "src.annotation.annotation_engine", "--resume"]},
    7: {"name": "Ensemble Review Merging & Export Gate", "cmd": [sys.executable, "-m", "src.review.export", "--output", "data/annotated/final_reviewed_merged.jsonl"]},
    8: {"name": "IAA & EDA Visualization", "cmd": [sys.executable, "-m", "src.evaluation.run_full_phase7"]},
    9: {"name": "Train/Val/Test Split & Exporter", "cmd": [sys.executable, "-m", "src.export.dataset_exporter"]},
    10: {"name": "Dataset Card & Datasheet Generation", "cmd": [sys.executable, "-m", "src.export.dataset_card"]},  # We chain sheet gen inside cmd list below
    11: {"name": "Run Unit Test Suite", "cmd": ["pytest"]}
}

def run_command(cmd: list[str]) -> bool:
    logger.info("Executing: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error("Command failed: %s with exit code %d", " ".join(cmd), e.returncode)
        return False
    except FileNotFoundError:
        logger.error("Executable not found for command: %s", " ".join(cmd))
        return False

def main():
    parser = argparse.ArgumentParser(description="Vietnamese Clickbait Dataset Pipeline Orchestrator")
    parser.add_argument("--run-all", action="store_true", help="Run the entire pipeline from scratch")
    parser.add_argument("--step", type=int, action="append", help="Specific step number(s) to run (can be repeated)")
    parser.add_argument("--list-steps", action="store_true", help="List all available steps and exit")
    args = parser.parse_args()

    if args.list_steps:
        print("\nAvailable Pipeline Steps:")
        print("=========================")
        for step_id, info in STEPS.items():
            print(f"  [{step_id:02d}] {info['name']}")
        print()
        return

    # Determine which steps to run
    steps_to_run = []
    if args.run_all:
        steps_to_run = sorted(STEPS.keys())
    elif args.step:
        steps_to_run = sorted(list(set(args.step)))
    else:
        # Default to showing help if no argument provided
        parser.print_help()
        print("\n* Hint: Use `python main.py --run-all` or `python main.py --step 7 --step 8` to start pipeline components.\n")
        return

    app_env = os.environ.get("APP_ENV", "dev")
    logger.info("Starting pipeline orchestration (Environment: %s). Running steps: %s", app_env, steps_to_run)

    for step_id in steps_to_run:
        if step_id not in STEPS:
            logger.error("Invalid step ID: %d. Skipping.", step_id)
            continue

        step_info = STEPS[step_id]
        print(f"\n============================================================")
        print(f" STEP {step_id:02d}: {step_info['name']}")
        print(f"============================================================\n")

        success = run_command(step_info["cmd"])
        if not success:
            logger.error("Pipeline stopped at Step %d (%s) due to failure.", step_id, step_info["name"])
            sys.exit(1)

        # Special post-execution chain for step 10 to generate datasheet
        if step_id == 10:
            logger.info("Chaining Datasheet Generation...")
            datasheet_success = run_command([sys.executable, "-m", "src.export.datasheet"])
            if not datasheet_success:
                logger.error("Datasheet generation failed.")
                sys.exit(1)

    print(f"\n============================================================")
    print(f" ALL RUNNING STEPS COMPLETED SUCCESSFULLY!")
    print(f"============================================================\n")

if __name__ == "__main__":
    main()
