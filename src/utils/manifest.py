import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

MANIFEST_PATH = Path(".manifest/raw_crawl_manifest.json")

def load_manifest() -> Dict[str, Any]:
    """
    Loads the crawl manifest from disk.
    Returns a default structure if the file does not exist.
    """
    if not MANIFEST_PATH.exists():
        return {"rss": {}, "sitemap": {}}

    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading manifest: {e}. Returning empty manifest.")
        return {"rss": {}, "sitemap": {}}

def save_manifest(manifest: Dict[str, Any]) -> None:
    """
    Saves the current manifest state to disk using an atomic write pattern.
    Ensures the .manifest directory exists.
    """
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MANIFEST_PATH.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        tmp_path.replace(MANIFEST_PATH)
    except IOError as e:
        print(f"Error saving manifest: {e}")

def mark_feed_processed(manifest: Dict[str, Any], source: str, feed_url: str, last_processed_url: Optional[str] = None, count: int = 0) -> None:
    """
    Updates the manifest dictionary for a specific RSS feed.
    Does NOT save to disk; caller should call save_manifest().
    """
    if source not in manifest["rss"]:
        manifest["rss"][source] = {}

    manifest["rss"][source][feed_url] = {
        "last_processed_url": last_processed_url,
        "count": count,
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

def mark_sitemap_processed(manifest: Dict[str, Any], source: str, sitemap_url: str, last_check: str, count: int = 0) -> None:
    """
    Updates the manifest dictionary for a specific Sitemap.
    Does NOT save to disk; caller should call save_manifest().
    """
    if source not in manifest["sitemap"]:
        manifest["sitemap"][source] = {}

    manifest["sitemap"][source][sitemap_url] = {
        "last_check": last_check,
        "count": count,
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

def get_feed_progress(source: str, feed_url: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves progress for a specific feed.
    """
    manifest = load_manifest()
    return manifest.get("rss", {}).get(source, {}).get(feed_url)

def get_sitemap_progress(source: str, sitemap_url: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves progress for a specific sitemap.
    """
    manifest = load_manifest()
    return manifest.get("sitemap", {}).get(source, {}).get(sitemap_url)
