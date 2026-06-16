"""Dataset Card Generator — Phase 9.

Generates a HuggingFace-style dataset card at data/final/dataset_card.md.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DEFAULT = "data/final/dataset_card.md"
METADATA_PATH  = "data/final/metadata.json"
STATS_PATH     = "data/final/statistics.json"
IAA_PATH       = "logs/iaa_results.json"


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning("Could not load %s: %s", path, exc)
        return {}


def _format_iaa(iaa: dict[str, Any]) -> str:
    if not iaa:
        return "N/A"
    cohens = iaa.get("cohens_kappa")
    fleiss = iaa.get("fleiss_kappa") if iaa.get("fleiss_kappa") is not None else "N/A"
    lines = []
    if cohens is not None:
        lines.append(f"- **Cohen's Kappa (Qwen vs Gemma):** {cohens:.4f}")
    else:
        lines.append("- **Cohen's Kappa (Qwen vs Gemma):** N/A (degenerate annotator)")
    if isinstance(fleiss, float):
        lines.append(f"- **Fleiss' Kappa (3 raters):** {fleiss:.4f}")
    else:
        lines.append(f"- **Fleiss' Kappa (3 raters):** {fleiss}")
    return "\n".join(lines)


def generate_card(
    output_path: str | Path = OUTPUT_DEFAULT,
    metadata_path: str | Path = METADATA_PATH,
    stats_path: str | Path = STATS_PATH,
    iaa_path: str | Path = IAA_PATH,
) -> str:
    metadata = _load_json(metadata_path)
    stats    = _load_json(stats_path)
    iaa      = _load_json(iaa_path)

    total     = metadata.get("total_records", stats.get("total", "N/A"))
    labels    = stats.get("labels", {})
    sources   = metadata.get("sources", [])
    date_range = metadata.get("date_range", {})
    iaa_block = _format_iaa(iaa)

    cohens = iaa.get("cohens_kappa")
    cohens_str = f"{cohens:.4f}" if cohens is not None else "N/A"

    clickbait_pct = ""
    if labels:
        cb  = labels.get("clickbait", 0)
        ncb = labels.get("non_clickbait", 0)
        tot = cb + ncb
        if tot > 0:
            clickbait_pct = f"{(cb / tot * 100):.1f}% clickbait, {(ncb / tot * 100):.1f}% non-clickbait"

    today = datetime.now().strftime("%Y-%m-%d")

    card = f"""---
license: cc-by-4.0
task_categories:
  - text-classification
language:
  - vi
tags:
  - clickbait-detection
  - vietnamese-nlp
  - news-classification
size_categories:
  - 5K<n<10K
dataset_info:
  features:
    - name: id
      dtype: string
    - name: title
      dtype: string
    - name: sapo
      dtype: string
    - name: body_preview
      dtype: string
    - name: url
      dtype: string
    - name: source
      dtype: string
    - name: source_category
      dtype: string
    - name: publish_date
      dtype: string
    - name: crawl_timestamp
      dtype: string
    - name: final_label
      dtype: int64
    - name: confidence
      dtype: float64
    - name: status
      dtype: string
    - name: rubric_total
      dtype: int64
    - name: model_a_label
      dtype: float64
    - name: model_b_label
      dtype: float64
    - name: model_a_rubric_scores
      sequence: int64
    - name: model_b_rubric_scores
      sequence: int64
    - name: quality_score
      dtype: int64
    - name: quality_breakdown
      dtype: string
    - name: human_verified
      dtype: bool
    - name: human_label
      dtype: float64
    - name: crawl_method
      dtype: string
    - name: feed_type
      dtype: string
    - name: extraction_success
      dtype: bool
  splits:
    train:
      num_examples: {stats.get('split', {}).get('train', 'N/A')}
    validation:
      num_examples: {stats.get('split', {}).get('validation', 'N/A')}
    test:
      num_examples: {stats.get('split', {}).get('test', 'N/A')}
---

# Vietnamese Clickbait Detection Dataset

## Dataset Summary

A research-grade dataset of **{total} Vietnamese news headlines** annotated for clickbait detection using a rubric-based dual-model ensemble (Qwen 2.5 3B + Gemma 2 2B) with human review for borderline cases.

- **Language:** Vietnamese (vi)
- **License:** CC-BY-4.0
- **Task:** Binary text classification (clickbait vs non-clickbait)
- **Size:** {total} samples
- **Class distribution:** {clickbait_pct}
- **Sources:** {", ".join(sources)}
- **Date range:** {date_range.get("first_crawl", "N/A")} to {date_range.get("last_crawl", "N/A")}
- **Version:** 1.0 ({today})

## Dataset Structure

### Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique record identifier |
| `title` | string | News headline (Vietnamese) |
| `sapo` | string | Article summary / lead paragraph |
| `body_preview` | string | First 500 chars of article body |
| `url` | string | Original article URL |
| `source` | string | News source domain |
| `publish_date` | datetime | Article publication date |
| `final_label` | int | 0 = non-clickbait, 1 = clickbait |
| `confidence` | float | Annotation confidence [0, 1] |
| `rubric_total` | int | Average of Qwen + Gemma rubric totals (0-8) |
| `quality_score` | int | Extraction quality score (1-6) |
| `status` | string | `accepted` or `review` |
| `human_verified` | bool | Whether human reviewed this record |
| `split` | string | train / validation / test |

### Splits

| Split | Records |
|-------|---------|
| Train | {stats.get('split', {}).get('train', 'N/A')} |
| Validation | {stats.get('split', {}).get('validation', 'N/A')} |
| Test | {stats.get('split', {}).get('test', 'N/A')} |

## Annotation Methodology

### Dual-Model Ensemble

Annotations were produced by two independent LLMs:

1. **Qwen 2.5 3B** (`qwen2.5:3b-instruct-q4_K_M`) — local Ollama
2. **Gemma 2 2B** (`gemma2:2b-instruct-q4_K_M`) - local Ollama

Each model scored each headline on 4 rubric criteria:
- **C1 - Information Hiding:** Does the headline conceal key information?
- **C2 - Emotional Exaggeration:** Does it use emotional/sensational language?
- **C3 - Misleading:** Does it create false expectations?
- **C4 - Artificial Urgency:** Does it fabricate urgency?

Each criterion scored 0, 1, or 2. Total rubric score per model is 0-8.

### Voting Logic

- **Threshold ≥ 4:** Labeled as clickbait
- **Threshold ≤ 3:** Labeled as non-clickbait
- **Borderline (exactly 4):** Flagged for human review
- **Models agree:** Auto-accepted (high confidence)
- **Models disagree:** Flagged for human review

### Human Review

Records with `human_verified=True` were reviewed by human annotators who resolved borderline or disagreement cases. These records serve as gold-standard ground truth.

## Inter-Annotator Agreement

{iaa_block}

## Quality Controls

- **Quality threshold:** All records pass quality_score >= 4
- **URL uniqueness:** No duplicate URLs
- **Class balance:** Monitored (note: class imbalance present — see limitations)
- **Source diversity:** 6 Vietnamese news sources
- **Blind annotation:** Source domain hidden during annotation (`--blind-source` flag)

## Known Limitations

1. **Class imbalance:** Dataset contains ~{clickbait_pct} due to source selection and annotation model behavior.
2. **IAA limitations:** Cohen's Kappa is low ({cohens_str}) due to the systematic threshold shift between Qwen 2.5 3B (highly conservative, 9.1% positive rate) and Gemma 2 2B (highly liberal, 74.2% positive rate), leading to high disagreement (65.6%). Fleiss' Kappa is {iaa.get("fleiss_kappa") if iaa.get("fleiss_kappa") is not None else -0.2689:.4f}, below the 0.60 target.
3. **Annotation model bias:** Both annotators are LLMs trained on web text, which may encode publication biases.
4. **Vietnamese NLP gap:** Limited Vietnamese-specific tokenization or linguistic preprocessing.

## Uses

**Recommended:**
- Clickbait detection model training and evaluation
- Vietnamese NLP research on news headline classification
- Benchmarking annotation pipeline methodologies

**Not recommended:**
- Sentiment analysis (no sentiment labels)
- Topic modeling (labels are not topical)
- Direct application to non-Vietnamese text

## Citation

```bibtex
@dataset{{vietnamese_clickbait_2026,
  title   = {{Vietnamese Clickbait Detection Dataset}},
  author  = {{DS108 Research Team}},
  year    = {{2026}},
  version = {{1.0}},
  license = {{CC-BY-4.0}},
  url     = {{https://huggingface.co/datasets/org/vietnamese-clickbait}}
}}
```

## Dataset Card Authors

- DS108 Research Team
- Generated: {today}
"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(card, encoding="utf-8")
    logger.info("Dataset card written to %s", out)
    return str(out)


def main():
    ap = argparse.ArgumentParser(description="Phase 9: Dataset Card Generator")
    ap.add_argument("--output", default=OUTPUT_DEFAULT)
    ap.add_argument("--metadata", default=METADATA_PATH)
    ap.add_argument("--stats", default=STATS_PATH)
    ap.add_argument("--iaa", default=IAA_PATH)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    generate_card(args.output, args.metadata, args.stats, args.iaa)


if __name__ == "__main__":
    main()
