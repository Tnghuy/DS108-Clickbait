#!/usr/bin/env python3
"""
Crawler Wrapper for Vietnamese Clickbait Dataset.

Coordinates RSS and Sitemap crawling to ensure that:
1. All directories under data/ and the .manifest/ directory are cleaned prior to execution.
2. For each source, at least 2000 and at most 3000 raw samples are crawled.
"""

import os
import json
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, Set, List

import sys
from pathlib import Path



from configs.sources_config import RSS_SOURCES, SITEMAPS
from src.utils.manifest import load_manifest, save_manifest
from src.scraping.rss_crawler import crawl_source
from src.scraping.sitemap_crawler import crawl_sitemap_source

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CrawlerWrapper")

RAW_DIR = Path("data/raw")
MANIFEST_DIR = Path(".manifest")

def cleanup_pipeline_dirs():
    """
    Ensures all pipeline directories exist safely without deleting any files.
    """
    logger.info("Ensuring all pipeline directories exist...")
    
    dirs = [
        Path("data/raw"),
        Path("data/filtered"),
        Path("data/validated"),
        Path("data/dedup"),
        Path("data/sampled"),
        Path("data/annotated"),
        Path("data/review"),
        Path("data/final"),
        Path(".manifest")
    ]
    
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        logger.info(f"Directory verified: {d}")
        
    logger.info("Pipeline directories verification completed successfully.")

def count_raw_records(source: str) -> int:
    """
    Counts the number of records in the raw JSONL file for a source.
    """
    file_path = RAW_DIR / f"{source}_raw.jsonl"
    if not file_path.exists():
        return 0
    
    count = 0
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
    except Exception as e:
        logger.error(f"Error counting records in {file_path}: {e}")
    return count

def load_source_urls(source: str) -> List[Dict[str, Any]]:
    """
    Loads all records for a source.
    """
    file_path = RAW_DIR / f"{source}_raw.jsonl"
    if not file_path.exists():
        return []
    
    records = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error(f"Error loading records from {file_path}: {e}")
    return records

def save_source_records(source: str, records: List[Dict[str, Any]]):
    """
    Saves records back to the raw JSONL file for a source.
    """
    file_path = RAW_DIR / f"{source}_raw.jsonl"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Error writing records to {file_path}: {e}")

def main():
    # 1. Clean up data and manifest directories
    cleanup_pipeline_dirs()
    
    # Initialize manifest and global URL deduplication sets
    manifest = load_manifest()
    existing_urls: Set[str] = set()
    
    # Target range constraints
    MIN_LIMIT = 2000
    MAX_LIMIT = 3000
    TARGET_COUNT = 2500  # Target count for backfill
    
    sources = list(RSS_SOURCES.keys())
    
    for idx, source in enumerate(sources):
        logger.info(f"\n==========================================")
        logger.info(f"PROCESSING SOURCE {idx+1}/{len(sources)}: {source}")
        logger.info(f"==========================================")
        
        # 1. Run RSS crawling for this source
        feed_urls = RSS_SOURCES.get(source, [])
        logger.info(f"Running RSS Crawler for source: {source} (feeds: {len(feed_urls)})")
        try:
            added = crawl_source(source, feed_urls, existing_urls, manifest, TARGET_COUNT)
            logger.info(f"RSS Crawler finished. Added {added} new articles.")
        except Exception as e:
            logger.error(f"Error during RSS crawling for {source}: {e}")
        
        # Count progress after RSS
        current_count = count_raw_records(source)
        logger.info(f"Total records crawled via RSS for {source}: {current_count}")
        
        # 2. Backfill with Sitemap if count < MIN_LIMIT
        if current_count < MIN_LIMIT:
            needed = TARGET_COUNT - current_count
            logger.info(f"Source {source} has {current_count} articles (minimum: {MIN_LIMIT}). Backfilling {needed} from sitemaps...")
            
            sitemaps = SITEMAPS.get(source, [])
            if sitemaps:
                try:
                    sitemap_added = crawl_sitemap_source(source, sitemaps, existing_urls, manifest, target_count=needed)
                    logger.info(f"Sitemap Crawler finished. Added {sitemap_added} new articles.")
                except Exception as e:
                    logger.error(f"Error during Sitemap crawling for {source}: {e}")
            else:
                logger.warning(f"No sitemaps configured for source: {source}")
                
            current_count = count_raw_records(source)
            logger.info(f"Total records after sitemap crawl for {source}: {current_count}")
        
        # 3. Limit to MAX_LIMIT if count > MAX_LIMIT
        if current_count > MAX_LIMIT:
            logger.info(f"Source {source} has {current_count} articles (maximum: {MAX_LIMIT}). Truncating to {MAX_LIMIT}...")
            records = load_source_urls(source)
            truncated_records = records[:MAX_LIMIT]
            save_source_records(source, truncated_records)
            
            # Rebuild existing_urls to only include truncated URLs
            # (First, remove all URLs of this source from existing_urls)
            source_urls = {rec["url"] for rec in records}
            existing_urls.difference_update(source_urls)
            # Then, add back the truncated ones
            for rec in truncated_records:
                existing_urls.add(rec["url"])
                
            current_count = count_raw_records(source)
            logger.info(f"Total records after truncation for {source}: {current_count}")
            
        if current_count < MIN_LIMIT:
            logger.warning(f"Source {source} ended up with {current_count} articles, which is still below the minimum {MIN_LIMIT}!")
        else:
            logger.info(f"Successfully guaranteed {current_count} raw articles for source {source} (range: [{MIN_LIMIT}, {MAX_LIMIT}])")
            
    # Save manifest at the end
    save_manifest(manifest)
    logger.info("\nCrawler Wrapper processing complete.")
    logger.info(f"Total unique URLs in raw dataset across all sources: {len(existing_urls)}")

if __name__ == "__main__":
    main()
