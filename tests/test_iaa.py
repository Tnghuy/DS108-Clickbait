import numpy as np
import pytest
from src.evaluation.iaa_calculator import calculate_gwets_ac1, calculate_krippendorff_alpha

def test_gwets_ac1_perfect_agreement():
    # Perfect agreement, balanced classes
    y1 = np.array([0, 1, 0, 1, 0, 1, 0, 1])
    y2 = np.array([0, 1, 0, 1, 0, 1, 0, 1])
    ac1 = calculate_gwets_ac1(y1, y2)
    assert ac1 == pytest.approx(1.0)

def test_gwets_ac1_perfect_disagreement():
    # Perfect disagreement, balanced classes
    y1 = np.array([0, 0, 0, 0])
    y2 = np.array([1, 1, 1, 1])
    ac1 = calculate_gwets_ac1(y1, y2)
    assert ac1 == pytest.approx(-1.0)

def test_gwets_ac1_class_imbalance():
    # High class imbalance where Cohen's Kappa would show paradox (low Kappa despite high agreement)
    y1 = np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 0])
    y2 = np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
    
    # Obs agreement = 0.9, but Kappa would be low due to unbalanced marginals
    # Gwet's AC1 should handle this gracefully (should be high)
    ac1 = calculate_gwets_ac1(y1, y2)
    assert ac1 > 0.75

def test_krippendorff_alpha_nominal_basic():
    # Ratings matrix: N samples by R raters with some NaNs (missing ratings)
    # 0, 1 ratings
    ratings = np.array([
        [0, 0, np.nan],
        [1, 1, 1],
        [0, 1, np.nan],
        [1, np.nan, 1],
        [0, 0, 0]
    ])
    
    alpha = calculate_krippendorff_alpha(ratings)
    # Assert alpha returns a valid float between -1.0 and 1.0
    assert -1.0 <= alpha <= 1.0

def test_krippendorff_alpha_perfect_agreement():
    ratings = np.array([
        [1, 1],
        [0, 0],
        [1, 1],
        [0, 0]
    ])
    alpha = calculate_krippendorff_alpha(ratings)
    assert alpha == pytest.approx(1.0)
