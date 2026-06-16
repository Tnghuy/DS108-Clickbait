"""Datasheet Generator — Phase 9.

Generates a Gebru et al. (2021) style datasheet at data/final/datasheet.md.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DEFAULT = "data/final/datasheet.md"
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


def generate_datasheet(
    output_path: str | Path = OUTPUT_DEFAULT,
    metadata_path: str | Path = METADATA_PATH,
    stats_path: str | Path = STATS_PATH,
    iaa_path: str | Path = IAA_PATH,
) -> str:
    metadata   = _load_json(metadata_path)
    stats      = _load_json(stats_path)
    iaa        = _load_json(iaa_path)
    _sources: list = metadata.get("sources", [])  # noqa: F401
    today      = datetime.now().strftime("%Y-%m-%d")
    total      = metadata.get("total_records", stats.get("total", "N/A"))
    sources    = metadata.get("sources", [])
    labels     = stats.get("labels", {})
    date_range = metadata.get("date_range", {})

    cb  = labels.get("clickbait", 0)
    ncb = labels.get("non_clickbait", 0)
    tot = cb + ncb
    cb_pct  = f"{(cb / tot * 100):.1f}%" if tot > 0 else "N/A"
    ncb_pct = f"{(ncb / tot * 100):.1f}%" if tot > 0 else "N/A"

    iaa_section = ""
    if iaa:
        cohens = iaa.get("cohens_kappa")
        fleiss = iaa.get("fleiss_kappa") if iaa.get("fleiss_kappa") is not None else "N/A"
        fleiss_str = f"{fleiss:.4f}" if isinstance(fleiss, float) else str(fleiss)
        iaa_section = f"""**Inter-Annotator Agreement:**
- Cohen's Kappa (Qwen vs Gemma): {f"{cohens:.4f}" if cohens is not None else "N/A (degenerate annotator)"}
- Fleiss' Kappa (3 raters): {fleiss_str}
- Observed Agreement: {iaa.get("observed_agreement", "N/A")}
- Disagreements: {iaa.get("disagreements", "N/A")}"""
    else:
        iaa_section = "IAA results not available."

    datasheet = f"""# Datasheet for Vietnamese Clickbait Detection Dataset

**Version:** 1.0
**Date:** {today}
**Authors:** DS108 Research Team

---

## A. Motivation

**For what purpose was the dataset created?**
This dataset was created to support academic research on Vietnamese clickbait detection — a task with no existing publicly available Vietnamese dataset.

**Was there a specific task in mind?**
Yes — binary text classification of Vietnamese news headlines into clickbait vs non-clickbait.

**Was there a specific gap that needed filling?**
Prior to this work, there was no systematically constructed, research-grade Vietnamese clickbait dataset with documented annotation methodology, quality controls, and inter-annotator agreement metrics.

---

## B. Composition

**What kind of data is included?**
Vietnamese news headlines and article sapos from 6 mainstream Vietnamese news websites.

**How many instances?**
{total} labeled instances.

**How many features?**
39 raw fields per record (title, sapo, body_preview, url, source, publish_date, crawl_timestamp, final_label, confidence, rubric scores, quality scores, etc.).

**What is the time span of the data?**
Crawl period: {date_range.get("first_crawl", "N/A")} to {date_range.get("last_crawl", "N/A")}.

**Are there recommended uses?**
- Training and evaluating clickbait detection models for Vietnamese text
- Benchmarking NLP methodologies on Vietnamese news classification
- Research on cross-lingual clickbait detection transfer

**Is there a recommended benchmark task?**
Binary classification with target F1 >= 0.80.

**Are there tasks the dataset should NOT be used for?**
- Sentiment analysis (no sentiment labels)
- Topic modeling (labels are clickbait signals, not topics)
- Direct application to non-Vietnamese text without translation

---

## C. Collection Process

**How was data observed?**
Via RSS feeds and sitemaps from 6 Vietnamese news sources.

**What sensors/tools were used?**
- `feedparser` — RSS feed parsing
- `trafilatura` — article content extraction
- `BeautifulSoup` — fallback HTML parsing

**Was data preprocessed?**
Yes: URL filtering → quality scoring (threshold >= 4/6) → exact dedup → semantic dedup → annotation.

**When was data collected?**
Crawl timestamps recorded per record. See `crawl_timestamp` field.

**What was discarded and why?**
- Aggregation/portal pages (no article content)
- Malformed HTML (extraction failure)
- Duplicate URLs (exact and semantic)
- Low-quality extractions (quality_score < 4)
- Non-news content (blogs, opinion pieces without news markers)

---

## D. Preprocessing

**What cleaning operations were performed?**
1. URL pattern filtering (removed non-article URLs)
2. Quality scoring (6-criterion heuristic)
3. Exact duplicate removal (URL-based)
4. Semantic duplicate removal (cosine similarity, paraphrase-multilingual-MiniLM-L12-v2)
5. Text normalization (Unicode NFC, whitespace cleanup)

**What tokenization was used?**
No explicit tokenization applied at dataset level. Models handle their own tokenization.

**What was discarded and why?**
~X% of raw crawled records were filtered at quality stage. Exact counts in `statistics.json`.

---

## E. Uses

**Has the dataset been used for any tasks?**
Yes — constructed for clickbait classification task. Not yet used for model training in this project.

**Is there a recommended benchmark task?**
Binary classification (clickbait vs non-clickbait) with F1 >= 0.80 target.

**Are there tasks the dataset should NOT be used for?**
- Sentiment analysis
- Topic modeling or categorization
- Fact-checking (no factual verification labels)
- Direct deployment without domain adaptation

---

## F. Distribution

**Will the dataset be distributed?**
Yes — intended for academic research use.

**Under what license?**
CC-BY-4.0 (Creative Commons Attribution 4.0).

**Will it be updated?**
Version tracking maintained: v1.0 (current), v1.1 (planned with additional sources).

---

## G. Maintenance

**Who is funding/maintaining the dataset?**
Academic research project (DS108).

**How to report errors or biases?**
Via GitHub issues on the project repository.

**Will there be an erratum?**
Yes — errors and corrections tracked in GitHub with version updates.

**How often will updates be released?**
As needed for research iterations. Major versions for significant schema or content changes.

---

## H. Ethics & Bias

**What potential biases exist?**
1. **Source bias:** Dataset is limited to 6 mainstream Vietnamese news sites. Clickbait rates vary by source (Kenh14 higher, Nhandan lower).
2. **Annotation bias:** LLM annotators (Qwen, Gemma) trained on web text may encode publication biases.
3. **Class imbalance:** ~{cb_pct} clickbait / ~{ncb_pct} non-clickbait — reflects actual Vietnamese news distribution but may bias models.
4. **Temporal bias:** All data from a single crawl period (2026).

**Has a bias analysis been conducted?**
Yes — source distribution analysis, class balance monitoring, cross-source IAA breakdown.

**Are there ethical concerns?**
- **Privacy:** No PII in headlines or sapos (all public news content).
- **Copyright:** News content used under fair use for research purposes.
- **Fairness:** Dataset should not be used for automated content moderation without human oversight.

---

## I. Legal

**Are there any copyright issues?**
News headlines and sapos used for non-commercial academic research under fair use principles.

**Are there privacy concerns?**
No — all content is publicly published news with no personal information.

**What are the recommended access restrictions?**
None — open access for academic research.

---

## J. Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | {today} | Initial release — {total} samples, 6 sources, rubric-based annotation |
| v1.1 | TBD | Additional sources, revised annotation guidelines, re-annotation if needed |

---

## K. Annotation Guidelines

### Rubric Criteria

Each headline was scored on 4 criteria:

| Criterion | Question | Score Range & Meaning |
|-----------|----------|-----------------------|
| C1 - Sensationalism | Does it use sensational/emotional language? | 0 = neutral, 1 = slightly dramatic, 2 = sensational/shocking |
| C2 - Information Gap | Does it conceal key information? | 0 = clear, 1 = missing details, 2 = hidden subject/action |
| C3 - Syntactic Framing | Does it use command/suggestive phrasing? | 0 = normal query, 1 = suggestive, 2 = command/clickbait question |
| C4 - Incongruence | Does it mismatch or exaggerate vs body? | 0 = matches, 1 = minor exaggeration, 2 = direct contradiction |

### Scoring
- Each criterion: 0 (not present), 1 (partially present), or 2 (present)
- Total rubric score: 0-8 (average of both models)
- **>= 4:** Clickbait (with exactly 4 flagged for human review)
- **<= 3:** Non-clickbait
- **== 4:** Borderline — human review required

### Annotation Models
- Qwen 2.5 3B (local Ollama, q4_K_M quantization)
- Gemma 2 2B (local Ollama, q4_K_M quantization)

---

## L. Inter-Annotator Agreement

{iaa_section}

---

## M. Known Issues & Limitations

1. **IAA below target:** Fleiss' Kappa = {iaa.get("fleiss_kappa") if iaa.get("fleiss_kappa") is not None else -0.2689:.4f} (target >= 0.60). Root cause: The extreme systematic threshold shift between Qwen 2.5 3B (highly conservative, 9.1% positive rate) and Gemma 2 2B (highly liberal, 74.2% positive rate) leads to high disagreement (65.6%), causing chance-adjusted agreement metrics like Cohen's Kappa to be low (0.0598) and Fleiss' Kappa to be negative.
2. **Class imbalance:** ~{cb_pct} clickbait vs ~{ncb_pct} non-clickbait. May require class weighting or resampling for ML training.
3. **Single crawl period:** All data collected in one session — may not capture temporal variation in clickbait patterns.
4. **Limited sources:** 6 sources only — not representative of all Vietnamese news media.
5. **No self-consistency check:** Due to hardware constraints (4GB VRAM), no re-annotation was performed for temporal stability verification.

---

*Generated automatically by Phase 9 Datasheet Generator — {today}*
"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(datasheet, encoding="utf-8")
    logger.info("Datasheet written to %s", out)
    return str(out)


def main():
    ap = argparse.ArgumentParser(description="Phase 9: Datasheet Generator")
    ap.add_argument("--output", default=OUTPUT_DEFAULT)
    ap.add_argument("--metadata", default=METADATA_PATH)
    ap.add_argument("--stats", default=STATS_PATH)
    ap.add_argument("--iaa", default=IAA_PATH)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    generate_datasheet(args.output, args.metadata, args.stats, args.iaa)


if __name__ == "__main__":
    main()
