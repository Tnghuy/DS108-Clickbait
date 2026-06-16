import pandas as pd
import numpy as np
import pytest
from src.export.dataset_exporter import assign_split, REQUIRED_FIELDS

@pytest.fixture
def synthetic_dataset():
    """Generates 1000 synthetic records with balanced clickbait ratio (25%) and spanned dates."""
    np.random.seed(42)
    n = 1000
    clickbait_ratio = 0.25 # 25% clickbait
    
    # 250 clickbait, 750 non-clickbait
    labels = [1] * 250 + [0] * 750
    
    # Publish dates spanning more than 60 days
    # 1620000000000 ms is roughly May 2021
    # We increment by 10,000,000 ms per step (approx 2.77 hours)
    # 1000 * 2.77 hours = 115 days (span > 60 days)
    dates = [1620000000000 + i * 10000000 for i in range(n)]
    
    records = []
    for i in range(n):
        records.append({
            "id": f"id_{i}",
            "title": f"Title of article {i}",
            "sapo": f"Sapo text of article {i} which should be reasonably long.",
            "body_preview": f"Body preview of article {i}",
            "url": f"http://example.com/article_{i}",
            "source": f"source_{i % 3}",
            "source_category": "mainstream",
            "publish_date": str(dates[i]),
            "crawl_timestamp": "2025-06-05T08:36:34Z",
            "final_label": labels[i],
            "confidence": 0.8,
            "status": "accepted",
            "rubric_total": 4,
            "model_a_label": float(labels[i]),
            "model_b_label": float(labels[i]),
            "model_a_rubric_scores": [1, 1, 1, 1],
            "model_b_rubric_scores": [1, 1, 1, 1],
            "quality_score": 5,
            "quality_breakdown": "{}",
            "human_verified": False,
            "human_label": float(labels[i]),
            "crawl_method": "rss",
            "feed_type": "news",
            "extraction_success": True,
        })
    return pd.DataFrame(records)

def test_stratified_split_ratio(synthetic_dataset):
    """Test that stratified temporal split keeps clickbait ratio within [expected_ratio ± 2%] (i.e. [23%, 27%])."""
    df_split = assign_split(synthetic_dataset)
    
    overall_ratio = synthetic_dataset["final_label"].mean() # should be 0.25
    assert overall_ratio == 0.25
    
    for split_name in ["train", "validation", "test"]:
        split_df = df_split[df_split["split"] == split_name]
        split_ratio = split_df["final_label"].mean()
        # Check that ratio is within expected_ratio ± 2%
        assert abs(split_ratio - overall_ratio) <= 0.02

def test_no_overlap(synthetic_dataset):
    """Test that there is no overlap of article URLs between splits."""
    df_split = assign_split(synthetic_dataset)
    
    train_urls = set(df_split[df_split["split"] == "train"]["url"])
    val_urls = set(df_split[df_split["split"] == "validation"]["url"])
    test_urls = set(df_split[df_split["split"] == "test"]["url"])
    
    assert train_urls.isdisjoint(val_urls)
    assert train_urls.isdisjoint(test_urls)
    assert val_urls.isdisjoint(test_urls)

def test_split_sizes(synthetic_dataset):
    """Test that split sizes sum up exactly to the total dataset size."""
    df_split = assign_split(synthetic_dataset)
    
    n_train = len(df_split[df_split["split"] == "train"])
    n_val = len(df_split[df_split["split"] == "validation"])
    n_test = len(df_split[df_split["split"] == "test"])
    
    assert n_train + n_val + n_test == len(synthetic_dataset)
    # Expected sizes for 1000 samples with source & class-level rounding:
    # Train: 706, Validation: 147, Test: 147
    assert n_train == 706
    assert n_val == 147
    assert n_test == 147

def test_output_schema(synthetic_dataset):
    """Test that all required output columns are present in the splits."""
    df_split = assign_split(synthetic_dataset)
    
    # Check that split column was added
    assert "split" in df_split.columns
    
    # Check that splits have all required fields for export
    for col in REQUIRED_FIELDS:
        assert col in df_split.columns
