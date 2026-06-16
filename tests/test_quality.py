import pytest
from src.validation.quality_scorer import QualityScorer

@pytest.fixture
def scorer():
    return QualityScorer(threshold=4)

@pytest.fixture
def valid_article():
    return {
        "title": "Tiêu đề bài viết hợp lệ và đủ dài",
        "sapo": "Đoạn sapo mở đầu bài viết hợp lệ và đạt độ dài trên 30 ký tự.",
        "body_preview": "Thân bài viết của chúng ta phải dài hơn 200 ký tự để vượt qua bộ lọc chất lượng cơ bản. Hãy đảm bảo rằng nội dung này đủ dài, không bị trùng lặp, không chứa quá nhiều liên kết và viết bằng tiếng Việt chuẩn.",
        "body": "Thân bài viết của chúng ta phải dài hơn 500 ký tự để đạt điểm tối đa cho tiêu chí độ dài. Hãy đảm bảo rằng nội dung này đủ dài, không bị trùng lặp, không chứa quá nhiều liên kết và viết bằng tiếng Việt chuẩn. Chúng tôi sẽ lặp đi lặp lại một số từ nhưng không quá nhiều để tránh vi phạm tỷ lệ TTR. Đây là đoạn văn bản bổ sung để tăng độ dài bài viết lên trên 500 ký tự."
    }

def test_score_range(scorer, valid_article):
    """Test that quality score is always within the expected range of [0, 6]."""
    score, breakdown = scorer.score_article(valid_article)
    assert 0 <= score <= 6
    assert isinstance(breakdown, dict)
    assert len(breakdown) == 6

def test_short_title_penalized(scorer, valid_article):
    """Test that titles shorter than 5 characters are penalized (forcing score to 0)."""
    # Normal article score
    normal_score, _ = scorer.score_article(valid_article)
    
    # Short title article
    short_title_article = valid_article.copy()
    short_title_article["title"] = "Ngắn" # 4 characters
    
    short_score, breakdown = scorer.score_article(short_title_article)
    
    assert breakdown["valid_title"] is False
    assert short_score == 0
    assert short_score < normal_score

def test_empty_content_rejected(scorer, valid_article):
    """Test that articles with empty critical fields are rejected (score = 0)."""
    # Empty title
    empty_title_article = valid_article.copy()
    empty_title_article["title"] = ""
    score1, _ = scorer.score_article(empty_title_article)
    assert score1 == 0
    
    # Empty sapo
    empty_sapo_article = valid_article.copy()
    empty_sapo_article["sapo"] = ""
    score2, _ = scorer.score_article(empty_sapo_article)
    assert score2 == 0
    
    # Empty body
    empty_body_article = valid_article.copy()
    empty_body_article["body_preview"] = ""
    empty_body_article["body"] = ""
    score3, _ = scorer.score_article(empty_body_article)
    assert score3 < 4 # Rejected because body preview check fails

def test_duplicate_title_content(scorer, valid_article):
    """Test that articles where title is identical to sapo are penalized (valid_sapo becomes False)."""
    duplicate_article = valid_article.copy()
    duplicate_article["title"] = "Tiêu đề trùng lặp hoàn toàn với sapo"
    duplicate_article["sapo"] = "Tiêu đề trùng lặp hoàn toàn với sapo"
    
    score, breakdown = scorer.score_article(duplicate_article)
    
    assert breakdown["valid_sapo"] is False
    assert score == 0 # because valid_sapo is False, which forces score to 0
