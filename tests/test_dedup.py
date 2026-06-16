import sys
from pathlib import Path
from unittest.mock import MagicMock, patch



import pytest

# Mock SentenceTransformer before importing SemanticDeduplicator
with patch('sentence_transformers.SentenceTransformer') as mock_transformer:
    mock_instance = MagicMock()
    mock_transformer.return_value = mock_instance
    from src.dedup.semantic_dedup import SemanticDeduplicator

def test_sentence_structure_penalty_identical():
    with patch('sentence_transformers.SentenceTransformer') as mock_transformer:
        mock_instance = MagicMock()
        mock_transformer.return_value = mock_instance
        deduper = SemanticDeduplicator()
        
        # Identical sentences
        p = deduper._get_sentence_structure_penalty("Hôm nay đi học.", "Hôm nay đi học.")
        assert p == pytest.approx(1.0)

def test_sentence_structure_penalty_length_ratio():
    with patch('sentence_transformers.SentenceTransformer') as mock_transformer:
        mock_instance = MagicMock()
        mock_transformer.return_value = mock_instance
        deduper = SemanticDeduplicator()
        
        # Length ratio > 1.5, same punctuation
        # s1: 32 chars, s2: 12 chars. Ratio = 32 / 12 = 2.67 > 1.5
        p = deduper._get_sentence_structure_penalty("Chúng ta cần phải dọn dẹp dự án.", "Dọn dẹp đi.")
        assert p == pytest.approx(0.8)

def test_sentence_structure_penalty_punctuation_difference():
    with patch('sentence_transformers.SentenceTransformer') as mock_transformer:
        mock_instance = MagicMock()
        mock_transformer.return_value = mock_instance
        deduper = SemanticDeduplicator()
        
        # Same length roughly, different punctuation (? vs .)
        # s1: 18 chars, s2: 18 chars.
        p = deduper._get_sentence_structure_penalty("Bạn ăn cơm chưa ạ?", "Hôm nay trời ấm áp.")
        assert p == pytest.approx(0.9)

def test_sentence_structure_penalty_both():
    with patch('sentence_transformers.SentenceTransformer') as mock_transformer:
        mock_instance = MagicMock()
        mock_transformer.return_value = mock_instance
        deduper = SemanticDeduplicator()
        
        # Length ratio > 1.5 AND punctuation differs (? vs .)
        # s1: 29 chars (ends with ?), s2: 9 chars (ends with .)
        # Penalty = 0.8 * 0.9 = 0.72
        p = deduper._get_sentence_structure_penalty("Hôm nay bạn có ăn cơm trưa chưa?", "Ăn cơm đi.")
        assert p == pytest.approx(0.72)
