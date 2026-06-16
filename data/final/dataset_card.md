---
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
      num_examples: 4212
    validation:
      num_examples: 894
    test:
      num_examples: 894
---

# Vietnamese Clickbait Detection Dataset

## Dataset Summary

A research-grade dataset of **6000 Vietnamese news headlines** annotated for clickbait detection using a rubric-based dual-model ensemble (Qwen 2.5 3B + Gemma 2 2B) with human review for borderline cases.

- **Language:** Vietnamese (vi)
- **License:** CC-BY-4.0
- **Task:** Binary text classification (clickbait vs non-clickbait)
- **Size:** 6000 samples
- **Class distribution:** 24.8% clickbait, 75.2% non-clickbait
- **Sources:** afamily, kenh14, nhandan, soha, thanhnien, tuoitre
- **Date range:** 2026-06-05T08:36:34.363453+00:00 to 2026-06-05T08:39:37.168790+00:00
- **Version:** 1.0 (2026-06-14)

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
| Train | 4212 |
| Validation | 894 |
| Test | 894 |

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

- **Cohen's Kappa (Qwen vs Gemma):** 0.0598
- **Fleiss' Kappa (3 raters):** -0.2689

## Quality Controls

- **Quality threshold:** All records pass quality_score >= 4
- **URL uniqueness:** No duplicate URLs
- **Class balance:** Monitored (note: class imbalance present — see limitations)
- **Source diversity:** 6 Vietnamese news sources
- **Blind annotation:** Source domain hidden during annotation (`--blind-source` flag)

## Known Limitations

1. **Class imbalance:** Dataset contains ~24.8% clickbait, 75.2% non-clickbait due to source selection and annotation model behavior.
2. **IAA limitations:** Cohen's Kappa is low (0.0598) due to the systematic threshold shift between Qwen 2.5 3B (highly conservative, 9.1% positive rate) and Gemma 2 2B (highly liberal, 74.2% positive rate), leading to high disagreement (65.6%). Fleiss' Kappa is -0.2689, below the 0.60 target.
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
@dataset{vietnamese_clickbait_2026,
  title   = {Vietnamese Clickbait Detection Dataset},
  author  = {DS108 Research Team},
  year    = {2026},
  version = {1.0},
  license = {CC-BY-4.0},
  url     = {https://huggingface.co/datasets/org/vietnamese-clickbait}
}
```

## Dataset Card Authors

- DS108 Research Team
- Generated: 2026-06-14
