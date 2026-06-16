import re
import logging
from urllib.parse import urlparse, urlunparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Patterns that explicitly identify non-article pages (Videos, Tags, Authors, AMP, Pagination, etc.)
REJECT_PATTERNS = [
    r'/video/',
    r'/tag/',
    r'/tags/',
    r'/author/',
    r'/amp$',
    r'/amp/',
    r'\?page=\d+',
    r'/page/\d+',
    r'#comment',
    r'/search\?',
    r'/tim-kiem/',
    r'/rss',
    r'/sitemap',
    r'\.rss$',
    r'\.xml$',
    r'/category/?$',
    r'/chuyen-muc/?$',
    r'/the-loai/?$',
    r'/photo/',
    r'/media/',
    r'/podcast/',
    r'/interactive/',
    r'/timeline/',
    r'/su-kien/',
    r'/chu-de/',
    r'/infographic/',
    r'/live/',
    r'/truc-tiep/',
    r'/tin-moi-nhat/?$'
]

# Pre-compile regex for performance
_REJECT_RE = [re.compile(p, re.IGNORECASE) for p in REJECT_PATTERNS]

def _normalize(url: str) -> str:
    """
    Normalize URL to prevent bypasses (scheme case, fragments, etc.)
    """
    if not url:
        return ""
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        fragment=""
    ))

def should_keep_url(url: str) -> bool:
    """
    Returns False if the URL matches any reject pattern, otherwise True.
    """
    if not url or not isinstance(url, str):
        return False

    normalized_url = _normalize(url)

    for p in _REJECT_RE:
        if p.search(normalized_url):
            logger.debug(f"Rejected [%s]: %s", p.pattern, url)
            return False
    return True

# Removed ARTICLE_INDICATORS and is_article_url as per review
