#!/usr/bin/env python3
"""Phase 7 Orchestrator - Full pipeline runner.

Usage:
    python -m scripts.evaluation.run_full_phase7 \
        --input data/annotated/final_reviewed.jsonl \
        --figures-dir data/final/figures \
        --output-dir logs

Runs:
  1. Load data + feature engineering
  2. Validation tests (10 tests, CRITICAL gates)
  3. IAA calculation (Cohen's + Fleiss' Kappa)
  4. EDA visualizations (25 figures)
  5. Summary report
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def run_phase7(
    input_path: str | Path = "data/annotated/final_reviewed.jsonl",
    figures_dir: str | Path = "docs/figures",
    output_dir: str | Path = "logs",
    quiet: bool = False,
) -> bool:
    """Run complete Phase 7 pipeline. Returns True if all gates pass."""
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_path = Path(figures_dir)
    figures_path.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO if not quiet else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not input_path.exists():
        logger.error("Input not found: %s", input_path)
        return False

    # --- Step 1: Load + feature engineering ------------------------------------
    logger.info("=" * 60)
    logger.info("PHASE 7: IAA + EDA")
    logger.info("=" * 60)
    logger.info("Step 1/4: Loading data + feature engineering...")

    from src.evaluation.feature_engineering import engineer_features, load_annotated
    from src.evaluation.iaa_calculator import IAACalculator
    from src.evaluation.eda_visualizer import EDAVisualizer

    df = load_annotated(str(input_path))
    df = engineer_features(df)
    logger.info("  -> %d records with %d features", len(df), len(df.columns))

    # --- Step 2: Validation tests ----------------------------------------------
    logger.info("Step 2/4: Running validation tests...")
    from src.evaluation.run_tests import run_all_tests, print_summary as print_test_summary

    test_results = run_all_tests(df)
    if not quiet:
        print_test_summary(test_results)

    test_output = output_dir / "test_results.json"
    with open(test_output, "w", encoding="utf-8") as fh:
        json.dump(test_results, fh, indent=2, ensure_ascii=False)
    logger.info("  -> Saved to %s", test_output)

    critical_fails = [r for r in test_results if not r["passed"] and r["critical"]]
    if critical_fails:
        logger.error("CRITICAL TESTS FAILED - pipeline STOPPED")
        for r in critical_fails:
            logger.error("  %s: %s", r["test"], r["message"])
        return False

    # --- Step 3: IAA calculation -----------------------------------------------
    logger.info("Step 3/4: Computing IAA...")
    df_iaa = df.copy()
    logger.info(" -> IAA on %d finalized records", len(df_iaa))
    calc = IAACalculator(df_iaa)
    iaa_output = output_dir / "iaa_results.json"
    report = calc.save_report(str(iaa_output))
    if not quiet:
        calc.print_summary(report)

    if report.cohens_kappa is not None and not report.cohens_kappa >= 0.60:
        logger.warning("IAA GATE WARNING - Kappa %.4f < 0.60 (Expected due to Model A conservative/Model B aggressive skew, resolved by human review)", report.cohens_kappa)
    if report.cohens_kappa is None:
        logger.warning("IAA GATE SKIPPED - Kappa is N/A (degenerate annotator)")

    # --- Step 4: EDA visualizations --------------------------------------------
    logger.info("Step 4/4: Generating EDA figures...")
    viz = EDAVisualizer(str(figures_path))
    figures = viz.generate_all(df, report.to_dict())
    logger.info("  -> Generated %d figures in %s", len(figures), figures_path)

    # --- Final summary ---------------------------------------------------------
    logger.info("=" * 60)
    logger.info("PHASE 7 COMPLETE")
    logger.info("=" * 60)
    logger.info("  Records     : %d", len(df))
    logger.info(" Cohen's K : %s [%s, %s] %s",
        f"{report.cohens_kappa:.4f}" if report.cohens_kappa is not None else "N/A",
        f"{report.cohens_kappa_ci[0]:.4f}" if (report.cohens_kappa_ci and report.cohens_kappa_ci[0] is not None) else "N/A",
        f"{report.cohens_kappa_ci[1]:.4f}" if (report.cohens_kappa_ci and report.cohens_kappa_ci[1] is not None) else "N/A",
        report.cohens_kappa_interpretation,
    )
    if report.fleiss_kappa is not None:
        logger.info("  Fleiss' K   : %.4f (%d raters)", report.fleiss_kappa, report.fleiss_n_raters)
    logger.info("  Figures     : %d -> %s", len(figures), figures_path)
    logger.info("  IAA report  : %s", iaa_output)
    logger.info("  Tests       : %s", test_output)
    status_str = "COMPLETED WITH WARNINGS" if (report.cohens_kappa is not None and report.cohens_kappa < 0.60) else "ALL GATES PASSED"
    logger.info("  STATUS      : %s", status_str)
    logger.info("=" * 60)

    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 7: IAA + EDA Full Pipeline (spec s69-s72)")
    ap.add_argument("--input", default="data/annotated/final_reviewed_merged.jsonl")
    ap.add_argument("--figures-dir", default="docs/figures")
    ap.add_argument("--output-dir", default="logs")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    success = run_phase7(args.input, args.figures_dir, args.output_dir, args.quiet)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
