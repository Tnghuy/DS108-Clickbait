#!/usr/bin/env python3
"""
RSS Crawler for Vietnamese Clickbait Dataset.

Crawls RSS feeds from configured sources and saves raw articles to JSONL files.
Features:
- Resumable crawling via manifest checkpoint
- Cross-feed deduplication using URL set
- Polite crawling with configurable delays
- Retry logic for transient errors
- Deterministic IDs using MD5 hash
"""

import json
import hashlib
import time
import logging
import re
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from dateutil import parser as date_parser

import feedparser

from configs.sources_config import RSS_SOURCES, SOURCE_CATEGORIES
from src.utils.manifest import (
    load_manifest,
    save_manifest,
    mark_feed_processed,
    get_feed_progress
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Retry configuration
RETRY_COUNT = 3
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]
SLEEP_BETWEEN_REQUESTS = 1.0
SLEEP_BETWEEN_SOURCES = 5.0

def normalize_url(url: str) -> str:
    """
    Normalizes a URL for consistent deduplication.
    - Remove trailing slash
    - Strip whitespace
    """
    if not url:
        return ""
    return url.strip().rstrip('/')

def generate_article_id(source: str, url: str) -> str:
    """
    Generates a deterministic ID from source and URL.
    Uses MD5 hash to ensure consistency across runs.
    """
    norm_url = normalize_url(url)
    url_hash = hashlib.md5(norm_url.encode('utf-8')).hexdigest()[:12]
    return f"{source}_{url_hash}"

def parse_feed_entry(entry, source: str, feed_url: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single feed entry into our raw schema.
    Returns None if the entry is invalid.
    """
    url = entry.get("link")
    if not url:
        logger.warning(f"Entry missing URL in feed {feed_url}")
        return None

    norm_url = normalize_url(url)

    # Parse publish date
    published_parsed = entry.get("published_parsed")
    publish_date = None

    if published_parsed:
        try:
            publish_date = datetime(*published_parsed[:6], tzinfo=timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass

    if not publish_date:
        # Fallback: try common date fields as raw strings
        for date_field in ["published", "updated", "dc:date", "pubDate"]:
            raw_date = entry.get(date_field)
            if raw_date:
                try:
                    dt = date_parser.parse(raw_date)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    publish_date = dt.isoformat()
                    break
                except (ValueError, TypeError, OverflowError):
                    continue

    # Extract feed type from feed URL
    # "https://dantri.com.vn/rss/thoi-su.rss" -> slug "thoi-su"
    slug = Path(feed_url).stem
    feed_type = re.sub(r"-\d+$", "", slug)

    record = {
        "id": generate_article_id(source, norm_url),
        "source": source,
        "url": norm_url,
        "title": entry.get("title", "").strip(),
        "sapo": (entry.get("summary", "") or entry.get("description", "")).strip(),
        "publish_date": publish_date,
        "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
        "crawl_method": "rss",
        "rss_feed": feed_url,
        "source_category": SOURCE_CATEGORIES.get(source, "unknown"),
        "feed_type": feed_type,
    }

    return record

def load_all_urls_from_raw() -> Set[str]:
    """
    Scans all existing raw JSONL files and builds a set of all URLs.
    This is used for cross-feed deduplication at startup.
    """
    logger.info("Loading existing URLs from raw data...")
    crawled_urls: Set[str] = set()

    if not RAW_DIR.exists():
        return crawled_urls

    for jsonl_file in RAW_DIR.glob("*_raw.jsonl"):
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        url = rec.get("url")
                        if url:
                            crawled_urls.add(normalize_url(url))
                    except json.JSONDecodeError:
                        continue
        except IOError as e:
            logger.error(f"Error reading {jsonl_file}: {e}")

    logger.info(f"Loaded {len(crawled_urls)} existing URLs.")
    return crawled_urls

def fetch_with_retry(url: str, retries: int = RETRY_COUNT) -> Optional[bytes]:
    """
    Fetches a URL with exponential backoff retry logic.
    Only retries on specific status codes (429, 5xx).
    Returns raw content bytes or None on failure.
    """
    import requests
    from requests.exceptions import RequestException

    backoff = 1.0
    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
            )

            if response.status_code == 200:
                return response.content

            if response.status_code in RETRY_STATUS_CODES:
                if attempt < retries - 1:
                    logger.warning(f"Attempt {attempt+1} failed for {url}: {response.status_code}. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                else:
                    logger.error(f"All retries exhausted for {url}: {response.status_code}")
            else:
                # Non-retryable status (403, 404, etc.)
                logger.error(f"Non-retryable status for {url}: {response.status_code}")
                break

        except RequestException as e:
            if attempt < retries - 1:
                logger.warning(f"Request error for {url}: {e}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error(f"All retries exhausted for {url}: {e}")

    return None

def crawl_source(source: str, feed_urls: List[str], existing_urls: Set[str], manifest: Dict[str, Any], target_count: int = 4000) -> int:
    """
    Crawls all RSS feeds for a single source.
    Returns the number of new articles added.
    """
    output_file = RAW_DIR / f"{source}_raw.jsonl"
    mode = "a" if output_file.exists() else "w"

    new_count = 0

    with open(output_file, mode, encoding="utf-8") as f:
        for idx, feed_url in enumerate(feed_urls):
            logger.info(f"Processing feed {idx+1}/{len(feed_urls)} for {source}: {feed_url}")

            # Fetch feed content
            content = fetch_with_retry(feed_url)
            if not content:
                logger.error(f"Failed to fetch feed: {feed_url}")
                continue

            # Parse feed
            try:
                feed_data = feedparser.parse(content)
            except Exception as e:
                logger.error(f"Failed to parse feed {feed_url}: {e}")
                continue

            if not feed_data.entries:
                logger.warning(f"Feed {feed_url} returned no entries")
                continue

            # Process entries
            feed_new_count = 0
            last_url_in_feed = None

            for entry in feed_data.entries:
                try:
                    record = parse_feed_entry(entry, source, feed_url)
                    if not record:
                        continue

                    norm_url = normalize_url(record["url"])

                    # Skip if already exists
                    if norm_url in existing_urls:
                        continue

                    # Validate record
                    from src.utils.schema import RawRecord, validate_record
                    # Safely handle float NaN publish_date if any (though usually str or None)
                    if "publish_date" in record and isinstance(record["publish_date"], float):
                        record["publish_date"] = None
                    if validate_record(record, RawRecord):
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        f.flush() # Force write to disk immediately for real-time tracking
                        feed_new_count += 1
                        new_count += 1
                        last_url_in_feed = norm_url
                        existing_urls.add(norm_url)
                    else:
                        logger.warning(f"Skipping record {record.get('id')} due to schema validation failure.")

                except Exception as e:
                    logger.error(f"Error processing entry in {feed_url}: {e}")
                    continue

            # Update manifest for this feed
            mark_feed_processed(
                manifest=manifest,
                source=source,
                feed_url=feed_url,
                last_processed_url=last_url_in_feed,
                count=feed_new_count
            )

            logger.info(f"  Added {feed_new_count} new articles from {feed_url}")

            # Sleep between requests (politeness)
            if idx < len(feed_urls) - 1:
                time.sleep(SLEEP_BETWEEN_REQUESTS)

    return new_count

def main():
    """
    Main crawling orchestration.
    """
    logger.info("Starting RSS crawl...")

    # Load all existing URLs for dedup
    existing_urls = load_all_urls_from_raw()

    # Load manifest once
    manifest = load_manifest()

    # Target records per source (configurable)
    TARGET_PER_SOURCE = 4000

    total_added = 0
    sources = list(RSS_SOURCES.items())

    for idx, (source, feed_urls) in enumerate(sources):
        logger.info(f"=== Crawling source {idx+1}/{len(sources)}: {source} ===")
        try:
            added = crawl_source(source, feed_urls, existing_urls, manifest, TARGET_PER_SOURCE)
            total_added += added
            logger.info(f"Source {source} completed. Added {added} new articles.")
        except Exception as e:
            logger.error(f"Critical error crawling {source}: {e}")
            continue

        # Sleep between sources (politeness)
        if idx < len(sources) - 1:
            logger.info(f"Sleeping {SLEEP_BETWEEN_SOURCES}s before next source...")
            time.sleep(SLEEP_BETWEEN_SOURCES)

    # Save manifest once at the end
    save_manifest(manifest)
    logger.info(f"RSS crawl complete. Total new articles: {total_added}")
    logger.info(f"Total unique URLs in raw: {len(existing_urls)}")

if __name__ == "__main__":
    main()
