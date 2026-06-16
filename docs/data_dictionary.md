# Data Dictionary: Vietnamese Clickbait Detection Dataset

**Version:** 1.0  
**Dataset:** `data/final/*.jsonl` (train/validation/test)

---

## Overview

Each record in the dataset is a JSON object with approximately 40 fields. Fields are grouped into categories:

1. **Identifiers & Metadata** — `id`, `url`, `source`, `publish_date`
2. **Content** — `title`, `sapo`, `body_preview`, `body_text`
3. **Extraction** — `extraction_success`, `quality_score`, `quality_breakdown`
4. **Annotation** — `final_label`, `confidence`, `rubric_total`, `severity`
5. **Model Outputs** — Qwen and Gemma individual predictions
6. **Human Review** — `human_verified`, `human_label`, `human_rubric_scores`
7. **Pipeline** — `crawl_timestamp`, `crawl_method`, `rss_feed`, `feed_type`
8. **Split** — `split`

---

## Field Reference

### Core Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | string | unique, non-null | Unique record identifier (format: `<source>_<md5>`). Example: `afamily_90e036548c0e`. |
| `title` | string | non-null, UTF-8 | Vietnamese news headline. Cleaned via `clean_text()`. |
| `sapo` | string | nullable | Article summary / lead paragraph. Fallback: first 200 chars of `body_text` if original sapo missing. |
| `body_preview` | string | non-null, ≤500 chars | First 500 characters of `body_text` (truncated with `...` if longer). |
| `body_text` | string | non-null, ≥150 chars | Full article body after boilerplate removal. Used for content validation. |
| `url` | string | non-null, unique | Original article URL. All URLs pass `should_keep_url()` filter. |

### Source & Temporal

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `source` | string | one of 6 values | News source domain: `afamily`, `kenh14`, `nhandan`, `soha`, `thanhnien`, `tuoitre`. |
| `source_category` | string | `formal_news` or `entertainment` | Source classification per `configs/sources_config.py`. |
| `publish_date` | string | ISO 8601 or NaN | Publication date as ISO 8601 string. Example: `2026-05-18T01:33:20+00:00`. |
| `crawl_timestamp` | string | ISO 8601 | Timestamp when this article was crawled. Example: `2026-05-24T17:37:05.830489+00:00`. |
| `crawl_method` | string | `rss` or `sitemap` | Method used to discover this URL. |
| `rss_feed` | float \| string | null if sitemap | RSS feed URL if discovered via RSS. |
| `feed_type` | float \| string | null if sitemap | Feed category (from RSS source configuration). |

### Extraction Quality

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `extraction_success` | bool | true only | Always `true` for final dataset (failed extractions filtered out earlier). |
| `quality_score` | int | [4, 6] | 6-criterion quality score sum: (1) valid title, (2) valid sapo, (3) body_preview exists, (4) sufficient length, (5) non-aggregation, (6) low repetition. |
| `quality_breakdown` | dict | 6 boolean keys | Detailed pass/fail for each criterion. Keys: `valid_title`, `valid_sapo`, `has_body_preview`, `sufficient_length`, `non_aggregation`, `low_repetition`. |

### Annotation

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `final_label` | float | 0.0 or 1.0 | Final binary label after ensemble voting + human review. |
| `confidence` | float | [0.0, 1.0] | Annotation confidence. Base = average of model confidences, ±0.1 adjustment for agreement. |
| `rubric_total` | int | [0, 8] | Average (rounded) of Qwen and Gemma total rubric scores. Formula: round((sum_A + sum_B) / 2), where each model scores C1+C2+C3+C4 ∈ [0,8]. Threshold: rubric_total ≥ 4 → clickbait (1), ≤ 3 → non-clickbait (0). |
| `severity` | int \| null | [0, 3] or null | Maximum severity score from Qwen and Gemma (0–3 scale). |
| `status` | string | `"accepted"` or `"review"` | Indicates if the record was auto-accepted by model consensus (`"accepted"`) or routed to review (`"review"`). |
| `human_verified` | bool | `true` or `false` | True if the record was manually reviewed and verified by a human; False if auto-accepted via model consensus. |
| `human_label` | int \| null | 0, 1, or null | Human-assigned label. Mostly `null` because most records were auto-accepted (no disagreement). |
| `human_rubric_scores` | list \| null | [0–2]×4 or null | Human rubric scores [C1,C2,C3,C4]. `null` for auto-accepted records. |
| `human_severity` | float \| null | [0–3] or null | Human severity score. `null` for auto-accepted records. |
| `human_notes` | string \| null | — | Annotator notes. Always `null` (no notes recorded). |
| `review_status` | string | `"auto_accepted"` or `"human_reviewed"` | Indicates if the record was auto-accepted by model consensus or reviewed and resolved by a human. |
| `review_timestamp` | string \| null | ISO 8601 or null | Timestamp when human reviewed (if applicable). `null` for auto-accepted records. |
| `reviewer_id` | string \| null | string or null | Identifier of the human reviewer (e.g., `"huy"`). `null` for auto-accepted records. |

### Model A (Qwen 2.5 3B)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `model_a_label` | int \| null | 0, 1, or null | Qwen's binary prediction. Stored as nullable integer to handle cases with missing annotations. |
| `model_a_confidence` | float | [0.0, 1.0] | Qwen's confidence. |
| `model_a_rubric_scores` | list[int] | 4 items, each [0,2] | Qwen's scores for C1–C4. |
| `model_a_severity` | int \| null | [0, 3] or null | Qwen's severity assessment. |
| `model_a_reason` | string | — | Qwen's reasoning text (Vietnamese). |

### Model B (Gemma 2 2B)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `model_b_label` | int \| null | 0, 1, or null | Gemma's binary prediction. Stored as nullable integer to handle cases with missing annotations. |
| `model_b_confidence` | float | [0.0, 1.0] | Gemma's confidence. |
| `model_b_rubric_scores` | list[int] | 4 items, each [0,2] | Gemma's scores for C1–C4. |
| `model_b_severity` | int \| null | [0, 3] or null | Gemma's severity assessment. |
| `model_b_reason` | string | — | Gemma's reasoning text (Vietnamese). |

### Split

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `split` | string | `"train"`, `"validation"`, or `"test"` | Train/validation/test split. Ratios: 70% / 15% / 15%. |

---

## Notes on Nullability

Many fields are `null` for auto-accepted records:

- `human_label`, `human_rubric_scores`, `human_severity`, `human_notes` — only populated if human reviewed.
- `review_timestamp`, `reviewer_id` — populated for the 3,968 manually reviewed records (e.g. `reviewer_id="huy"`); `null` for auto-accepted records.
- `rss_feed`, `feed_type` — `null` for sitemap-sourced records.
- `human_rubric_scores` — stored as `null` (Python `NoneType`) when not applicable, not empty list `[]`.

---

## Quality Guarantees

All 6,000 final records satisfy:

- ✅ `title` is non-empty, valid UTF-8
- ✅ `url` is unique across dataset
- ✅ `final_label` ∈ {0.0, 1.0}
- ✅ `quality_score` ∈ [4, 6]
- ✅ `confidence` ∈ [0.0, 1.0]
- ✅ `rubric_scores` arrays have length 4 with values ∈ [0, 2]
- ✅ `human_verified` correctly indicates review status (`true` for human_reviewed, `false` for auto_accepted)
- ✅ `status == "accepted"`

See `src/evaluation/run_tests.py` for the full validation suite.

---

## Data Integrity

- **No duplicate URLs:** Enforced by exact + semantic deduplication.
- **No null titles:** Filtered during quality validation.
- **Valid UTF-8:** All text fields pass `json.dumps(ensure_ascii=False)`.
- **Split integrity:** No record appears in more than one split.

---

## Conversion Notes

### Date Format

`publish_date` is stored as an ISO 8601 string. To convert to Python `datetime`:

```python
import pandas as pd
df['publish_date_dt'] = pd.to_datetime(df['publish_date'], errors='coerce')
```

### Loading Parquet

Parquet files preserve all field types exactly (including `null` vs `[]` distinctions). CSV/JSONL may show `NaN` for nulls.

