"""Dataset Export - Phase 8."""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

INPUT_DEFAULT  = "data/annotated/final_reviewed_merged.jsonl"
OUTPUT_DIR     = "data/final"
FIGURES_DIR    = "docs/figures"
IAA_RESULTS    = "logs/iaa_results.json"
TEST_RESULTS   = "logs/test_results.json"

SPLIT_DIRS     = ("train", "validation", "test")
FORMATS        = ("csv", "jsonl", "parquet")
REQUIRED_FIELDS = [
    "id", "title", "sapo", "body_preview", "url", "source",
    "source_category", "publish_date", "crawl_timestamp",
    "final_label", "confidence", "status",
    "rubric_total", "model_a_label", "model_b_label",
    "model_a_rubric_scores", "model_b_rubric_scores",
    "quality_score", "quality_breakdown",
    "human_verified", "human_label",
    "crawl_method", "feed_type", "extraction_success",
]


def assign_split(df):
    df = df.copy()
    pub = pd.to_datetime(pd.to_numeric(df["publish_date"], errors="coerce"), unit="ms")
    # Detect unusable date range (all same month, or all pre-2020)
    date_range_span = (pub.max() - pub.min()).days if not pub.isna().all() else -1
    usable_dates = not pub.isna().all() and date_range_span > 60

    if not usable_dates:
        logger.warning("Dates unusable (span=%d days) — using random split", date_range_span)
        df["split"] = "train"
        for (source, label), group in df.groupby(["source", "final_label"], dropna=False):
            rng = group.sample(frac=1.0, random_state=42).index
            n = len(rng)
            n_val = int(n * 0.15)
            n_test = int(n * 0.15)
            val_idx = rng[:n_val]
            test_idx = rng[n_val : n_val + n_test]
            train_idx = rng[n_val + n_test :]
            df.loc[val_idx, "split"] = "validation"
            df.loc[test_idx, "split"] = "test"
            df.loc[train_idx, "split"] = "train"
    else:
        logger.info("Using stratified temporal split based on publish_date (span=%d days)", date_range_span)
        df["parsed_pub_date"] = pub
        df["split"] = "train"
        for (source, label), group in df.groupby(["source", "final_label"], dropna=False):
            group_sorted = group.sort_values(by="parsed_pub_date", ascending=True)
            n = len(group_sorted)
            n_val = int(n * 0.15)
            n_test = int(n * 0.15)
            n_train = n - n_val - n_test
            val_idx = group_sorted.index[n_train : n_train + n_val]
            test_idx = group_sorted.index[n_train + n_val :]
            train_idx = group_sorted.index[: n_train]
            df.loc[val_idx, "split"] = "validation"
            df.loc[test_idx, "split"] = "test"
            df.loc[train_idx, "split"] = "train"
        df = df.drop(columns=["parsed_pub_date"])
        
    logger.info("Split: train=%d, validation=%d, test=%d",
        (df["split"] == "train").sum(),
        (df["split"] == "validation").sum(),
        (df["split"] == "test").sum())
    return df


def run_validation(input_path, test_results_path):
    from src.evaluation.run_tests import run_all_tests, print_summary
    with open(input_path, encoding="utf-8") as fh:
        records = [json.loads(l) for l in fh if l.strip()]
    df = pd.DataFrame(records)
    results = run_all_tests(df)
    print_summary(results)
    critical_fails = [r for r in results if not r["passed"] and r["critical"]]
    if critical_fails:
        logger.error("%d CRITICAL test(s) FAILED", len(critical_fails))
        return False
    out = Path(test_results_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    return True


def _select_fields(df):
    cols = [c for c in REQUIRED_FIELDS if c in df.columns]
    extra = [c for c in df.columns if c not in cols]
    return df[cols + extra]


def _clean_val(v):
    if v is None:
        return None
    if isinstance(v, (list, dict, np.ndarray)):
        return v
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        return v.item()
    return v


def _export_split(df_split, fmt, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df_split = df_split.copy()

    # Format publish_date to ISO 8601 string if present
    if "publish_date" in df_split.columns:
        pub_dt = pd.to_datetime(pd.to_numeric(df_split["publish_date"], errors="coerce"), unit="ms", utc=True)
        df_split["publish_date"] = pub_dt.dt.strftime("%Y-%m-%dT%H:%M:%S%z")

    # Cast nullable integer columns to Pandas Int64 to maintain integer representation with null support
    for col in ["model_a_label", "model_b_label", "human_label", "severity", "model_a_severity", "model_b_severity", "human_severity"]:
        if col in df_split.columns:
            df_split[col] = df_split[col].astype("Int64")

    # Cast human notes to string
    if "human_notes" in df_split.columns:
        df_split["human_notes"] = df_split["human_notes"].astype("string")

    if fmt == "csv":
        df_split.to_csv(path, index=False, encoding="utf-8-sig")
    elif fmt == "jsonl":
        records = df_split.to_dict(orient="records")
        with open(path, "w", encoding="utf-8") as fh:
            for rec in records:
                cleaned_rec = {k: _clean_val(v) for k, v in rec.items()}
                fh.write(json.dumps(cleaned_rec, ensure_ascii=False) + "\n")
    elif fmt == "parquet":
        df_split.to_parquet(path, index=False)
    logger.info("  -> %s (%d records)", path, len(df_split))


def export_splits(df, out_dir):
    out_dir = Path(out_dir)
    summary = {}
    for split_name in SPLIT_DIRS:
        split_df = df[df["split"] == split_name].copy()
        if len(split_df) == 0:
            logger.warning("Split '%s' is empty", split_name)
            continue
        split_df = _select_fields(split_df)
        summary[split_name] = {"records": len(split_df)}
        for fmt in FORMATS:
            ext = {"jsonl": "jsonl"}.get(fmt, fmt)
            fpath = out_dir / f"{split_name}.{ext}"
            _export_split(split_df, fmt, fpath)
            summary[split_name][fmt] = str(fpath)
    return summary


def build_metadata(df, iaa_path):
    iaa = {}
    try:
        with open(iaa_path, encoding="utf-8") as fh:
            iaa = json.load(fh)
    except Exception:
        logger.warning("IAA results not found: %s", iaa_path)
    label_dist = df["final_label"].value_counts().to_dict() if "final_label" in df.columns else {}
    source_dist = df["source"].value_counts().to_dict() if "source" in df.columns else {}
    return {
        "total_records": len(df),
        "label_distribution": {str(k): int(v) for k, v in label_dist.items()},
        "source_distribution": {str(k): int(v) for k, v in source_dist.items()},
        "quality_threshold": 4,
        "annotation_models": ["qwen2.5:3b-instruct-q4_K_M", "gemma2:2b-instruct-q4_K_M"],
        "annotation_method": "rubric-based dual-model ensemble with human review",
        "iaa": iaa,
        "sources": sorted(df["source"].unique().tolist()) if "source" in df.columns else [],
        "date_range": {
            "first_crawl": str(df["crawl_timestamp"].min()) if "crawl_timestamp" in df.columns else None,
            "last_crawl":  str(df["crawl_timestamp"].max()) if "crawl_timestamp" in df.columns else None,
        },
        "fields": REQUIRED_FIELDS,
    }


def build_sources_metadata(df):
    if "source" not in df.columns:
        return {}
    sources = {}
    for src, grp in df.groupby("source"):
        sources[str(src)] = {
            "records": len(grp),
            "clickbait_count": int((grp["final_label"] == 1).sum()) if "final_label" in grp.columns else 0,
            "non_clickbait_count": int((grp["final_label"] == 0).sum()) if "final_label" in grp.columns else 0,
            "avg_quality": round(grp["quality_score"].mean(), 2) if "quality_score" in grp.columns else None,
        }
    return sources


def build_statistics(df) -> dict[str, Any]:
    stats: dict[str, Any] = {"total": len(df)}
    if "final_label" in df.columns:
        stats["labels"] = {
            "clickbait":     int((df["final_label"] == 1).sum()),
            "non_clickbait": int((df["final_label"] == 0).sum()),
        }
    if "quality_score" in df.columns:
        stats["quality"] = {
            "mean": round(df["quality_score"].mean(), 2),
            "min":  int(df["quality_score"].min()),
            "max":  int(df["quality_score"].max()),
        }
    if "confidence" in df.columns:
        stats["confidence"] = {
            "mean": round(df["confidence"].mean(), 4),
            "min":  round(df["confidence"].min(), 4),
            "max":  round(df["confidence"].max(), 4),
        }
    if "status" in df.columns:
        stats["status"] = df["status"].value_counts().to_dict()
    if "human_verified" in df.columns:
        stats["human_verified_count"] = int(df["human_verified"].sum())
    if "split" in df.columns:
        stats["split"] = df["split"].value_counts().to_dict()
    return stats


def export_dataset(
    input_path=INPUT_DEFAULT,
    output_dir=OUTPUT_DIR,
    figures_dir=FIGURES_DIR,
    iaa_results_path=IAA_RESULTS,
    test_results_path=TEST_RESULTS,
    skip_validation=False,
):
    input_path  = Path(input_path)
    output_dir  = Path(output_dir)
    figures_dir = Path(figures_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading %s ...", input_path)
    records = []
    with open(input_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    df = pd.DataFrame(records)
    logger.info("Loaded %d records, %d columns", len(df), len(df.columns))

    if not skip_validation:
        logger.info("Running validation tests ...")
        if not run_validation(input_path, test_results_path):
            sys.exit(1)
    else:
        logger.info("Skipping validation")

    df = assign_split(df)

    logger.info("Exporting splits ...")
    export_summary = export_splits(df, output_dir)

    logger.info("Writing metadata ...")
    meta = build_metadata(df, iaa_results_path)
    with open(output_dir / "metadata.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)

    src_meta = build_sources_metadata(df)
    with open(output_dir / "sources.json", "w", encoding="utf-8") as fh:
        json.dump(src_meta, fh, indent=2, ensure_ascii=False)

    stats = build_statistics(df)
    with open(output_dir / "statistics.json", "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2, ensure_ascii=False)

    fig_src = Path("docs/figures")
    if fig_src.exists() and fig_src.resolve() != figures_dir.resolve():
        for fpath in fig_src.glob("*.png"):
            shutil.copy2(fpath, figures_dir / fpath.name)
        logger.info("Copied %d figures", len(list(figures_dir.glob("*.png"))))

    report = {
        "phase": "Phase 8 - Export",
        "input": str(input_path),
        "output_dir": str(output_dir),
        "total_records": len(df),
        "splits": export_summary,
        "statistics": stats,
        "export_cleared": True,
    }
    with open(output_dir / "export_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    # Run baseline model training
    logger.info("Running baseline models training...")
    try:
        import subprocess
        result = subprocess.run([sys.executable, "src/evaluation/baseline_models.py"], check=True)
        if result.returncode == 0:
            logger.info("Baseline models training finished successfully.")
        else:
            logger.error("Baseline models training failed.")
    except Exception as e:
        logger.error(f"Error executing baseline models training: {e}")

    logger.info("=" * 60)
    logger.info("PHASE 8 EXPORT COMPLETE")
    logger.info("=" * 60)
    for split_name, info in export_summary.items():
        logger.info("  %s: %d records", split_name, info["records"])
    logger.info("Output: %s", output_dir)
    return report


def main():
    ap = argparse.ArgumentParser(description="Phase 8: Dataset Export")
    ap.add_argument("--input", default=INPUT_DEFAULT)
    ap.add_argument("--output-dir", default=OUTPUT_DIR)
    ap.add_argument("--figures-dir", default=FIGURES_DIR)
    ap.add_argument("--iaa-results", default=IAA_RESULTS)
    ap.add_argument("--test-results", default=TEST_RESULTS)
    ap.add_argument("--skip-validation", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    export_dataset(
        input_path=args.input,
        output_dir=args.output_dir,
        figures_dir=args.figures_dir,
        iaa_results_path=args.iaa_results,
        test_results_path=args.test_results,
        skip_validation=args.skip_validation,
    )


if __name__ == "__main__":
    main()
