"""Data Validation Tests - Phase 7 (spec §72).

10 mandatory tests:
- 3 CRITICAL: block export if fail (URL uniqueness, label validity, no nulls)
- 7 non-critical: log warnings

Usage:
    python -m scripts.evaluation.run_tests \\
        --input data/annotated/final_reviewed.jsonl \\
        --output logs/test_results.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def _to_int(val: Any) -> int:
    if hasattr(val, "item"):
        return int(val.item())
    return int(val)


def _result(name: str, passed: bool, critical: bool, message: str) -> dict[str, Any]:
    if passed:
        status = "PASS"
    elif critical:
        status = "FAIL (CRITICAL)"
    else:
        status = "WARN"
    return {
        "test": name,
        "passed": passed,
        "critical": critical,
        "message": message,
        "status": status,
    }


def test_url_uniqueness(df: pd.DataFrame) -> Tuple[bool, str]:
    """CRITICAL: No duplicate URLs."""
    dup_urls = _to_int(df["url"].duplicated().sum())
    passed = (dup_urls == 0)
    msg = f"{dup_urls} duplicate URL(s) found"
    return passed, msg


def test_label_validity(df: pd.DataFrame) -> Tuple[bool, str]:
    """CRITICAL: All finalized labels must be 0 or 1.
    Records in 'review' status that are still pending human decision (null final_label) are excluded."""
    if "status" in df.columns and "final_label" in df.columns:
        df = df[~((df["status"] == "review") & (df["final_label"].isna()))]
    n_total = _to_int(len(df))
    invalid = _to_int(df["final_label"].apply(lambda x: x not in (0, 1)).sum())
    none_count = _to_int(df["final_label"].isna().sum())
    passed = (invalid == 0) and (none_count == 0)
    msg = f"{invalid} invalid labels, {none_count} None label(s) (of {n_total} finalized)"
    return passed, msg


def test_no_nulls(df: pd.DataFrame) -> Tuple[bool, str]:
    """CRITICAL: Required fields must not be null (excluding pending review-queue records)."""
    if "status" in df.columns and "final_label" in df.columns:
        df = df[~((df["status"] == "review") & (df["final_label"].isna()))]
    required = ["title", "source", "url", "final_label", "quality_score"]
    null_counts = {col: _to_int(df[col].isna().sum()) for col in required if col in df.columns}
    total_nulls = sum(null_counts.values())
    passed = (total_nulls == 0)
    msg = f"Null counts: {null_counts}"
    return passed, msg


def test_quality_scores(df: pd.DataFrame) -> Tuple[bool, str]:
    """Non-critical: All records should have quality_score >= 4."""
    if "quality_score" not in df.columns:
        return False, "quality_score column missing"
    below = _to_int((df["quality_score"] < 4).sum())
    total = len(df)
    pct = (below / total) * 100 if total > 0 else 0.0
    passed = (below == 0)
    msg = f"{below}/{total} records below threshold (>=4), {pct:.1f}%"
    return passed, msg


def test_source_balance(df: pd.DataFrame) -> Tuple[bool, str]:
    """Non-critical: Each source 8-20% of dataset."""
    if "source" not in df.columns:
        return False, "source column missing"
    counts = df["source"].value_counts(normalize=True) * 100
    violations = counts[(counts < 8) | (counts > 20)]
    passed = len(violations) == 0
    dist = {k: f"{v:.1f}%" for k, v in counts.round(1).items()}
    msg = f"Source distribution: {dist}"
    if not passed:
        viol = {k: f"{v:.1f}%" for k, v in violations.round(1).items()}
        msg += f" | Violations: {viol}"
    return passed, msg


def test_class_balance(df: pd.DataFrame) -> Tuple[bool, str]:
    """Non-critical: Each class 45-55%."""
    if "final_label" not in df.columns:
        return False, "final_label column missing"
    pct = df["final_label"].value_counts(normalize=True) * 100
    violations = pct[(pct < 45) | (pct > 55)]
    passed = len(violations) == 0
    dist = {int(k): f"{v:.1f}%" for k, v in pct.round(1).items()}
    msg = f"Class distribution: {dist}"
    return passed, msg


def test_confidence_scores(df: pd.DataFrame) -> Tuple[bool, str]:
    """Non-critical: Confidence in [0, 1]."""
    if "confidence" not in df.columns:
        return False, "confidence column missing"
    out_of_range = _to_int(((df["confidence"] < 0.0) | (df["confidence"] > 1.0)).sum())
    passed = (out_of_range == 0)
    msg = f"{out_of_range} score(s) out of [0, 1] range"
    return passed, msg


def test_utf8_encoding(df: pd.DataFrame) -> Tuple[bool, str]:
    """Non-critical: All text fields valid UTF-8."""
    text_cols = ["title", "sapo", "body_preview"]
    issues = 0
    for col in text_cols:
        if col not in df.columns:
            continue
        try:
            df[col].astype(str).str.encode("utf-8").str.decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            issues += 1
    passed = (issues == 0)
    msg = f"{issues} encoding issue(s) in {text_cols}"
    return passed, msg


def test_timestamps(df: pd.DataFrame) -> Tuple[bool, str]:
    """Non-critical: Timestamps valid and reasonable."""
    if "crawl_timestamp" not in df.columns:
        return False, "crawl_timestamp column missing"
    dates = pd.to_datetime(df["crawl_timestamp"], errors="coerce")
    null_dates = _to_int(dates.isna().sum())
    future_dates = _to_int((dates > pd.Timestamp.now(tz=dates.dt.tz)).sum())
    too_old = _to_int((dates < pd.Timestamp("2020-01-01", tz=dates.dt.tz)).sum())
    issues = null_dates + future_dates + too_old
    passed = (issues == 0)
    msg = f"Null: {null_dates}, Future: {future_dates}, Pre-2020: {too_old}"
    return passed, msg


def test_body_preview_length(df: pd.DataFrame) -> Tuple[bool, str]:
    """Non-critical: Body preview >= 50 chars."""
    if "body_preview" not in df.columns:
        return False, "body_preview column missing"
    short = _to_int((df["body_preview"].astype(str).str.len() < 50).sum())
    passed = (short == 0)
    msg = f"{short} record(s) with body_preview < 50 chars"
    return passed, msg


ALL_TESTS = [
    ("URL uniqueness", test_url_uniqueness, True),
    ("Label validity", test_label_validity, True),
    ("No nulls in required fields", test_no_nulls, True),
    ("Quality score >= 4", test_quality_scores, False),
    ("Source balance (8-20%)", test_source_balance, False),
    ("Class balance (45-55%)", test_class_balance, False),
    ("Confidence score range [0,1]", test_confidence_scores, False),
    ("UTF-8 encoding", test_utf8_encoding, False),
    ("Valid timestamps", test_timestamps, False),
    ("Body preview >= 50 chars", test_body_preview_length, False),
]


def run_all_tests(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Run all 10 tests, return list of result dicts."""
    results = []
    for name, fn, is_critical in ALL_TESTS:
        try:
            passed, msg = fn(df)
        except Exception as exc:
            passed = False
            msg = f"ERROR: {exc}"
            logger.exception("Test '%s' raised an exception", name)
        results.append(_result(name, passed, is_critical, msg))
    return results


def print_summary(results: list[dict[str, Any]]) -> None:
    """Print human-readable summary."""
    critical_fails = [r for r in results if not r["passed"] and r["critical"]]
    warns = [r for r in results if not r["passed"] and not r["critical"]]
    passes = [r for r in results if r["passed"]]

    print("\n============================================================")
    print(f" VALIDATION RESULTS: {len(passes)}/{len(results)} passed")
    print("============================================================\n")

    for r in passes:
        print(f"  [PASS]      {r['test']}")

    for r in warns:
        print(f"  [WARN]      {r['test']}: {r['message']}")

    for r in critical_fails:
        print(f"  [FAIL-CRIT] {r['test']}: {r['message']}")

    if critical_fails:
        print(f"\n  >>> {len(critical_fails)} CRITICAL TEST(S) FAILED — export blocked")
    else:
        print("\n  >>> All critical tests passed — export CLEARED")
    print("============================================================\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 7: Data validation tests (spec §72)")
    ap.add_argument("--input", default="data/annotated/final_reviewed.jsonl")
    ap.add_argument("--output", default="logs/test_results.json")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        sys.exit(1)

    logger.info("Loading %s ...", input_path)
    records = []
    with open(input_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    df = pd.DataFrame(records)
    logger.info("Loaded %d records, %d columns", len(df), len(df.columns))

    results = run_all_tests(df)

    if not args.quiet:
        print_summary(results)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    logger.info("Results saved to %s", out)

    critical_fails = [r for r in results if not r["passed"] and r["critical"]]
    if critical_fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
