#!/usr/bin/env python3
"""
Sitemap Crawler for Vietnamese Clickbait Dataset.

Crawls sitemaps to collect historical URLs that may not be present in RSS feeds.
Features:
- Recursive parsing of sitemap indexes
- Date-based filtering using <lastmod>
- Cross-deduplication with existing raw data
- Unified schema output for downstream extraction
"""

import json
import hashlib
import time
import logging
import warnings
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# Filter out the annoying XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from configs.sources_config import SITEMAPS, SOURCE_CATEGORIES
from src.utils.manifest import (
    load_manifest,
    save_manifest,
    mark_sitemap_processed,
    get_sitemap_progress
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
RETRY_COUNT = 3
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]
SLEEP_BETWEEN_REQUESTS = 1.0
SLEEP_BETWEEN_SOURCES = 5.0

# Global session for connection pooling (Performance boost)
http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

def normalize_url(url: str) -> str:
    if not url:
        return ""
    # Preserve case for path as some servers are case-sensitive,
    # but normalize whitespace and trailing slashes
    return url.strip().rstrip('/')

def generate_article_id(source: str, url: str) -> str:
    norm_url = normalize_url(url)
    url_hash = hashlib.md5(norm_url.encode('utf-8')).hexdigest()[:12]
    return f"{source}_{url_hash}"

def parse_w3c_datetime(date_str: str) -> Optional[datetime]:
    """
    Parses W3C datetime strings commonly found in sitemaps.
    Handles both 'YYYY-MM-DD' and 'YYYY-MM-DDTHH:MM:SS+ZZ:ZZ'.
    """
    if not date_str:
        return None

    date_str = date_str.strip()
    try:
        # Try ISO format first
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        try:
            # Try date-only format
            return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning(f"Could not parse date string: {date_str}")
            return None

def fetch_with_retry(url: str, retries: int = RETRY_COUNT) -> Optional[str]:
    backoff = 1.0
    for attempt in range(retries):
        try:
            # Use session and tuple timeout (connect, read) to prevent hanging
            response = http_session.get(
                url,
                timeout=(5, 25),
                headers=http_session.headers
            )
            if response.status_code == 200:
                return response.text

            logger.warning(f"Request failed for {url}: Status {response.status_code}. Attempt {attempt+1}/{retries}")
            if response.status_code in RETRY_STATUS_CODES:
                if attempt < retries - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
            break
        except requests.RequestException as e:
            if attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error(f"Request failed for {url}: {e}")
    return None

def parse_sitemap(url: str, depth: int = 0, max_depth: int = 5, max_urls: int = 10000) -> List[Dict]:
    """
    Parses a sitemap XML. If it's a sitemap index, it recursively parses child sitemaps.
    Returns a list of {loc, lastmod} dictionaries.
    """
    content = fetch_with_retry(url)
    if not content:
        return []

    # Use 'html.parser' as a robust fallback for XML sitemaps
    # to avoid dependencies on lxml and handle namespace issues.
    soup = BeautifulSoup(content, 'html.parser')
    logger.debug(f"Parsing content from {url}. Tag count: {len(soup.find_all())}")
    results = []

    # Use a lambda to find tags regardless of XML namespace
    sitemap_indexes = soup.find_all(lambda tag: tag.name == 'sitemap')
    if sitemap_indexes:
        if depth >= max_depth:
            logger.warning(f"Max sitemap depth reached at {url}")
            return []

        logger.info(f"Detected sitemap index at {url}. Parsing child sitemaps...")
        for index in sitemap_indexes:
            if len(results) >= max_urls:
                logger.info(f"Reached max_urls limit ({max_urls}) during sitemap index traversal. Stopping early.")
                break
            loc = index.find(lambda tag: tag.name == 'loc')
            if loc:
                child_url = loc.text.strip()
                logger.info(f"  -> Fetching child sitemap: {child_url}")
                # Recursive call with increased depth
                child_results = parse_sitemap(child_url, depth=depth + 1, max_depth=max_depth, max_urls=max_urls - len(results))
                results.extend(child_results)
                time.sleep(SLEEP_BETWEEN_REQUESTS)
        return results

    # Otherwise, it's a regular sitemap
    # Use a more aggressive search to bypass any remaining namespace issues
    all_tags = soup.find_all()
    urls = [tag for tag in all_tags if tag.name and tag.name.endswith('url')]

    for u in urls:
        # Find loc and lastmod tags inside the url tag, also bypassing namespaces
        loc = next((tag for tag in u.find_all() if tag.name and tag.name.endswith('loc')), None)
        lastmod = next((tag for tag in u.find_all() if tag.name and tag.name.endswith('lastmod')), None)

        if loc:
            results.append({
                "loc": loc.text.strip(),
                "lastmod": lastmod.text.strip() if lastmod else None
            })

    return results

def load_all_urls_from_raw() -> Set[str]:
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
        except IOError:
            continue
    return crawled_urls

def crawl_sitemap_source(source: str, sitemap_urls: List[str], existing_urls: Set[str], manifest: Dict[str, Any], target_count: int = 4000) -> int:
    output_file = RAW_DIR / f"{source}_raw.jsonl"
    mode = "a" if output_file.exists() else "w"
    new_count = 0
    duplicate_count = 0

    # Cutoff for sitemap historical data (e.g., 365 days)
    # Removed filter to collect all historical data

    with open(output_file, mode, encoding="utf-8") as f:
        for sitemap_url in sitemap_urls:
            # Check target before starting a new sitemap
            if new_count >= target_count:
                logger.info(f"Target of {target_count} reached for {source}. Stopping sitemap crawl.")
                break

            logger.info(f"Processing sitemap for {source}: {sitemap_url}")

            # Check manifest progress
            progress = get_sitemap_progress(source, sitemap_url)
            last_check = progress.get("last_check") if progress else None

            remaining_needed = max(2000, (target_count - new_count) * 3)
            entries = parse_sitemap(sitemap_url, max_urls=remaining_needed)
            source_new_count = 0

            for entry in entries:
                # Check target during entry processing
                if new_count >= target_count:
                    logger.info(f"Target of {target_count} reached during sitemap processing. Stopping.")
                    break

                url = entry["loc"]
                norm_url = normalize_url(url)

                if norm_url in existing_urls:
                    duplicate_count += 1
                    if duplicate_count % 100 == 0:
                        logger.info(f"  [SKIP] Found {duplicate_count} duplicates so far...")
                    continue


                lastmod_str = entry["lastmod"]
                lastmod_dt = parse_w3c_datetime(lastmod_str)

                # Filter by checkpoint date
                if lastmod_dt and last_check:
                    try:
                        checkpoint_dt = datetime.fromisoformat(last_check)
                        if lastmod_dt <= checkpoint_dt:
                            logger.info(f"  [SKIP] Old date ({lastmod_dt}) <= checkpoint ({checkpoint_dt}): {norm_url}")
                            continue
                    except ValueError:
                        pass

                # Removed 365-day filter to collect all historical data

                # Build unified schema record


                # Build unified schema record
                record = {
                    "id": generate_article_id(source, norm_url),
                    "source": source,
                    "url": norm_url,
                    "title": None, # To be filled by extractor
                    "sapo": None, # To be filled by extractor
                    "publish_date": lastmod_dt.isoformat() if lastmod_dt else None,
                    "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
                    "crawl_method": "sitemap",
                    "rss_feed": None,
                    "source_category": SOURCE_CATEGORIES.get(source, "unknown"),
                    "feed_type": None,
                }

                # Validate record
                from src.utils.schema import RawRecord, validate_record
                if "publish_date" in record and isinstance(record["publish_date"], float):
                    record["publish_date"] = None
                if validate_record(record, RawRecord):
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno()) # Force write to physical disk
                    source_new_count += 1
                    new_count += 1
                    if new_count % 100 == 0:
                        logger.info(f"  ... added {new_count} URLs so far for {source}")
                    existing_urls.add(norm_url)
                else:
                    logger.warning(f"Skipping sitemap record {record.get('id')} due to schema validation failure.")

            if new_count >= target_count:
                break # Exit the sitemap_urls loop entirely

            # Update manifest only if the sitemap was fully processed without hitting the target limit
            mark_sitemap_processed(
                manifest=manifest,
                source=source,
                sitemap_url=sitemap_url,
                last_check=datetime.now(timezone.utc).isoformat(),
                count=source_new_count
            )
            logger.info(f"  Sitemap {sitemap_url} done: Added {source_new_count}, Skipped {duplicate_count} duplicates.")
            time.sleep(SLEEP_BETWEEN_REQUESTS)

    return new_count

def main():
    logger.info("Starting Sitemap crawl...")
    existing_urls = load_all_urls_from_raw()

    # Load manifest
    manifest = load_manifest()

    # Target records per source (configurable)
    TARGET_PER_SOURCE = 4000

    total_added = 0

    for idx, (source, sitemaps) in enumerate(SITEMAPS.items()):
        logger.info(f"=== Processing source {idx+1}/{len(SITEMAPS)}: {source} ===")
        try:
            added = crawl_sitemap_source(source, sitemaps, existing_urls, manifest, TARGET_PER_SOURCE)
            total_added += added
            logger.info(f"Source {source} completed. Added {added} new URLs.")
        except Exception as e:
            logger.error(f"Critical error crawling sitemaps for {source}: {e}")
            continue

        if idx < len(SITEMAPS) - 1:
            time.sleep(SLEEP_BETWEEN_SOURCES)

    # Save manifest at the end
    save_manifest(manifest)
    logger.info(f"Sitemap crawl complete. Total new records: {total_added}")

if __name__ == "__main__":
    main()
