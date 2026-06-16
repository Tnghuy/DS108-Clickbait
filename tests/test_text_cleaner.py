import sys
from pathlib import Path



from src.utils.text_cleaner import clean_text, truncate_text, extract_title_from_html

def test_clean_text_none():
    assert clean_text(None) is None

def test_clean_text_unicode_normalization():
    # Decomposed "á" (a + combining acute accent) should normalize to NFC "á"
    decomposed = "a\u0301"
    normalized = clean_text(decomposed)
    assert normalized == "á"

def test_clean_text_html_entities():
    raw_text = "Tin tức &amp; Sự kiện &quot;Nóng&quot;"
    cleaned = clean_text(raw_text)
    assert cleaned == 'Tin tức & Sự kiện "Nóng"'

def test_clean_text_whitespace_collapse():
    raw_text = "   Tin    tức     nóng \n  trong  ngày   "
    cleaned = clean_text(raw_text)
    assert cleaned == "Tin tức nóng trong ngày"

def test_clean_text_mojibake_replacement():
    raw_text = "“Tin tức” – Cập nhật…"
    cleaned = clean_text(raw_text)
    assert cleaned == '"Tin tức" - Cập nhật...'

def test_truncate_text():
    text = "Đây là một đoạn văn bản rất dài cần được cắt ngắn để hiển thị preview."
    # Truncate at 10 chars
    truncated = truncate_text(text, max_length=10, suffix="...")
    assert truncated == "Đây là một..."
    
    # Text shorter than max_length should remain unchanged
    short_text = "Ngắn"
    assert truncate_text(short_text, max_length=10) == "Ngắn"
    
    # None input
    assert truncate_text(None) is None

def test_extract_title_from_html_h1():
    html_content = "<html><body><h1>Tiêu đề bài viết nóng hổi</h1><p>Nội dung</p></body></html>"
    title = extract_title_from_html(html_content)
    assert title == "Tiêu đề bài viết nóng hổi"

def test_extract_title_from_html_og_title():
    html_content = '<html><head><meta property="og:title" content="Tiêu đề Facebook OG" /></head></html>'
    title = extract_title_from_html(html_content)
    assert title == "Tiêu đề Facebook OG"

def test_extract_title_from_html_title_tag():
    html_content = "<html><head><title>Tiêu đề Trang Web - Tên Báo Điện Tử</title></head></html>"
    title = extract_title_from_html(html_content)
    assert title == "Tiêu đề Trang Web"
