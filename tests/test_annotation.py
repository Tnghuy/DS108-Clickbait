import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import requests



from src.annotation.clients.qwen_client import QwenLocalClient
from src.annotation.clients.gemma_client import GemmaLocalClient
from src.annotation.voting import calculate_rubric_vote


def test_client_health_check_success():
    """Test health check passes when Ollama returns the target model."""
    client = QwenLocalClient(endpoint="http://localhost:11434")
    client.model_id = "qwen2.5:3b-instruct-q4_K_M"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "qwen2.5:3b-instruct-q4_K_M"}]
    }

    with patch("requests.get", return_value=mock_resp):
        res = client.health_check()
        assert client._health_checked is True
        assert "models" in res
        assert res["models"][0]["name"] == "qwen2.5:3b-instruct-q4_K_M"


def test_client_health_check_offline():
    """Test health check raises RuntimeError when Ollama is unreachable."""
    client = QwenLocalClient(endpoint="http://invalid-localhost:11434")
    
    with patch("requests.get", side_effect=requests.ConnectionError("Connection refused")):
        with pytest.raises(RuntimeError) as exc_info:
            client.health_check()
        assert "Please make sure Ollama is running" in str(exc_info.value)


def test_client_health_check_missing_model():
    """Test health check raises RuntimeError when target model is not installed in Ollama."""
    client = QwenLocalClient(endpoint="http://localhost:11434")
    client.model_id = "gemma2:2b-instruct-q4_K_M"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "some-other-model:latest"}]
    }

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(RuntimeError) as exc_info:
            client.health_check()
        assert "not found in Ollama" in str(exc_info.value)
        assert "some-other-model:latest" in str(exc_info.value)


def test_client_annotate_success():
    """Test annotate method parses Ollama JSON response, handles Qwen thinking block and BARS normalization."""
    client = QwenLocalClient(endpoint="http://localhost:11434")
    client.model_id = "qwen2.5:3b-instruct-q4_K_M"
    client.options["system_prompt"] = "System: {title} | {sapo}"

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    
    # Mock Ollama output with thinking tags and JSON response
    mock_post_resp.json.return_value = {
        "response": '{"label": 1, "confidence": 0.85, "rubric_scores": [2, 1, 1, 0], "severity": 2, "reason": "Tiêu đề chứa từ giật gân Sốc"}',
        "thinking": "<think>Phân tích cú pháp tiêu đề có yếu tố phóng đại</think>"
    }

    with patch("requests.post", return_value=mock_post_resp):
        res = client.annotate("Sốc: Phát hiện phương pháp mới!", "Sapo của bài viết.")
        
        assert res["label"] == 1
        assert res["confidence"] == pytest.approx(0.85)
        assert res["rubric_scores"] == [2, 1, 1, 0]
        assert res["severity"] == 2
        assert "Sốc" in res["reason"]
        assert isinstance(res["thought_process"], dict)
        assert res["thought_process"]["external_reasoning"] == "<think>Phân tích cú pháp tiêu đề có yếu tố phóng đại</think>"


def test_client_annotate_failure():
    """Test annotate method gracefully returns default failure payload upon request exception."""
    client = GemmaLocalClient(endpoint="http://localhost:11434")
    client.model_id = "gemma2:2b-instruct-q4_K_M"
    client.options["system_prompt"] = "System: {title}"

    with patch("requests.post", side_effect=requests.Timeout("Request timed out")):
        res = client.annotate("Tiêu đề mẫu", "Sapo mẫu")
        assert res["label"] is None
        assert res["confidence"] == 0.0
        assert res["rubric_scores"] == [0, 0, 0, 0]
        assert "Error:" in res["reason"]


def test_voting_borderline():
    """Test that voting flags borderline cases correctly for human review."""
    model_a_res = {
        "label": 0,
        "confidence": 0.8,
        "rubric_scores": [1, 1, 1, 0],  # total = 3
        "severity": 0
    }
    model_b_res = {
        "label": 1,
        "confidence": 0.9,
        "rubric_scores": [2, 1, 1, 0],  # total = 4
        "severity": 1
    }

    label, status, confidence, rubric_total, severity = calculate_rubric_vote(
        model_a_res, model_b_res, {}
    )

    assert label == 1  # 3.5 rounded is 4 -> 1
    assert status == "review"  # model disagreement or borderline (3, 4)
    assert rubric_total == 4
    assert severity == 1
