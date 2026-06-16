"""
sources_config.py — Centralized source configuration.

Thay thế dict SOURCES trong scraper.py bằng:
    from sources_config import RSS_SOURCES, SITEMAPS

NOTES:
- RSS_SOURCES: ~30–40 feed/nguồn → ~600–800 bài/lần chạy/nguồn
- SITEMAPS: sitemap index XML → hàng chục nghìn bài lịch sử
- Một số URL RSS có thể thay đổi theo thời gian; kiểm tra lại nếu feed trả về 404.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# RSS FEEDS — nhiều category mỗi nguồn
# ─────────────────────────────────────────────────────────────────────────────

RSS_SOURCES: dict[str, list[str]] = {

    # ── Tuổi Trẻ ─────────────────────────────────────────────────
    "tuoitre": [
        "https://tuoitre.vn/rss/tin-moi-nhat.rss",
        "https://tuoitre.vn/rss/thoi-su.rss",
        "https://tuoitre.vn/rss/the-gioi.rss",
        "https://tuoitre.vn/rss/kinh-doanh.rss",
        "https://tuoitre.vn/rss/cong-nghe.rss",
        "https://tuoitre.vn/rss/xe.rss",
        "https://tuoitre.vn/rss/van-hoa.rss",
        "https://tuoitre.vn/rss/giai-tri.rss",
        "https://tuoitre.vn/rss/the-thao.rss",
        "https://tuoitre.vn/rss/phap-luat.rss",
        "https://tuoitre.vn/rss/giao-duc.rss",
        "https://tuoitre.vn/rss/suc-khoe.rss",
        "https://tuoitre.vn/rss/du-lich.rss",
        "https://tuoitre.vn/rss/gia-that.rss",
        "https://tuoitre.vn/rss/khoa-hoc.rss",
    ],

    # ── Nhân Dân ──────────────────────────────────────────────────
    "nhandan": [
        "https://nhandan.vn/rss/home.rss",
        "https://nhandan.vn/rss/chinhtri-1171.rss",
        "https://nhandan.vn/rss/xa-luan-1176.rss",
        "https://nhandan.vn/rss/kinhte-1185.rss",
        "https://nhandan.vn/rss/chungkhoan-1191.rss",
        "https://nhandan.vn/rss/vanhoa-1251.rss",
        "https://nhandan.vn/rss/xahoi-1211.rss",
        "https://nhandan.vn/rss/phapluat-1287.rss",
        "https://nhandan.vn/rss/du-lich-1257.rss",
        "https://nhandan.vn/rss/thegioi-1231.rss",
        "https://nhandan.vn/rss/thethao-1224.rss",
        "https://nhandan.vn/rss/giaoduc-1303.rss",
        "https://nhandan.vn/rss/y-te-1309.rss",
        "https://nhandan.vn/rss/khoahoc-congnghe-1292.rss",
        "https://nhandan.vn/rss/moi-truong-1296.rss",
    ],

    # ── Thanh Niên ────────────────────────────────────────────────
    "thanhnien": [
        "https://thanhnien.vn/rss/home.rss",
        "https://thanhnien.vn/rss/thoi-su.rss",
        "https://thanhnien.vn/rss/chinh-tri.rss",
        "https://thanhnien.vn/rss/the-gioi.rss",
        "https://thanhnien.vn/rss/kinh-te.rss",
        "https://thanhnien.vn/rss/doi-song.rss",
        "https://thanhnien.vn/rss/suc-khoe.rss",
        "https://thanhnien.vn/rss/gioi-tre.rss",
        "https://thanhnien.vn/rss/giao-duc.rss",
        "https://thanhnien.vn/rss/du-lich.rss",
        "https://thanhnien.vn/rss/van-hoa.rss",
        "https://thanhnien.vn/rss/giai-tri.rss",
        "https://thanhnien.vn/rss/the-thao.rss",
        "https://thanhnien.vn/rss/cong-nghe.rss",
        "https://thanhnien.vn/rss/xe.rss",
    ],

    # ── Kenh14 ────────────────────────────────────────────────────
    "kenh14": [
        "https://kenh14.vn/rss/home.rss",
        "https://kenh14.vn/star.rss",
        "https://kenh14.vn/hoc-duong.rss",
        "https://kenh14.vn/beauty-fashion.rss",
        "https://kenh14.vn/cine.rss",
        "https://kenh14.vn/musik.rss",
        "https://kenh14.vn/the-gioi-do-day.rss",
        "https://kenh14.vn/doi-song.rss",
        "https://kenh14.vn/tek-life.rss",
        "https://kenh14.vn/xem-mua-luon.rss",
        "https://kenh14.vn/money14.rss",
        "https://kenh14.vn/sport.rss",
        "https://kenh14.vn/xa-hoi.rss",
        "https://kenh14.vn/an-choi-di.rss",
        "https://kenh14.vn/suc-khoe.rss",
        "https://kenh14.vn/the-30s.rss",
    ],

    # ── Soha ───────────────────────────────────────────────────────
    "soha": [
        "https://soha.vn/rss/home.rss",
        "https://soha.vn/rss/thoi-su-xa-hoi.rss",
        "https://soha.vn/rss/kinh-doanh.rss",
        "https://soha.vn/rss/quoc-te.rss",
        "https://soha.vn/rss/the-thao.rss",
        "https://soha.vn/rss/nhip-song-moi.rss",
        "https://soha.vn/rss/giai-tri.rss",
        "https://soha.vn/rss/phap-luat.rss",
        "https://soha.vn/rss/song-khoe.rss",
        "https://soha.vn/rss/xe.rss",
        "https://soha.vn/rss/cong-nghe.rss",
        "https://soha.vn/rss/doi-song.rss",
        "https://soha.vn/rss/the-gioi.rss",
    ],

    # ── Afamily ────────────────────────────────────────────────────
    "afamily": [
        "https://afamily.vn/trang-chu.rss",
        "https://afamily.vn/lifestyle.rss",
        "https://afamily.vn/xa-hoi.rss",
        "https://afamily.vn/dep.rss",
        "https://afamily.vn/me-va-be.rss",
        "https://afamily.vn/giao-duc.rss",
        "https://afamily.vn/suc-khoe.rss",
        "https://afamily.vn/tieu-dung.rss",
        "https://afamily.vn/an-ngon.rss",
        "https://afamily.vn/tam-su-gia-dinh.rss",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# SOURCE CATEGORIES
# ─────────────────────────────────────────────────────────────────────────────

SOURCE_CATEGORIES: dict[str, str] = {
    "tuoitre": "formal_news",
    "nhandan": "formal_news",
    "thanhnien": "formal_news",
    "kenh14": "entertainment",
    "soha": "entertainment",
    "afamily": "entertainment",
}

SITEMAPS: dict[str, list[str]] = {
    "tuoitre":    ["https://tuoitre.vn/sitemaps/index.rss"],
    "nhandan":    ["https://nhandan.vn/sitemap.xml"],
    "thanhnien":  ["https://thanhnien.vn/sitemap.xml"],
    "kenh14":     ["https://kenh14.vn/sitemap.xml"],
    "soha":       ["https://soha.vn/sitemap.xml"],
    "afamily":    ["https://afamily.vn/sitemap.xml"],
}