"""Text cleaning utilities for Vietnamese news content."""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Optional


def _fix_mojibake(text: str) -> str:
    """Fix common mojibake patterns from mis-encoded UTF-8."""
    replacements = {
        "“": '"',  # left double quotation mark
        "”": '"',  # right double quotation mark
        "‘": "'",  # left single quotation mark
        "’": "'",  # right single quotation mark / apostrophe
        "–": "-",  # en dash
        "—": "-",  # em dash
        "…": "...",  # horizontal ellipsis
        "�": "",  # replacement character (strip)
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def _decode_latin1_utf8(text: str) -> str:
    """Attempt to recover UTF-8 from Latin-1-misinterpreted bytes."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def clean_text(text: Optional[str]) -> Optional[str]:
    """Normalize Unicode, decode HTML entities, and clean whitespace.

    Parameters
    ----------
    text : str or None
        Raw text to clean.  May contain Latin-1-misinterpreted UTF-8 bytes
        or HTML entities.

    Returns
    -------
    str or None
        Cleaned text, or None if input was None.
    """
    if text is None:
        return None

    # Recover UTF-8 if text arrived as Latin-1 byte characters
    text = _decode_latin1_utf8(text)

    # Normalize Unicode (NFC): combine decomposed chars
    text = unicodedata.normalize("NFC", text)

    # Decode HTML entities: &amp; -> &, &quot; -> ", &agrave; -> à
    text = html.unescape(text)

    # Fix common mojibake (curly quotes, em-dashes, replacement chars)
    text = _fix_mojibake(text)

    # Strip leading/trailing whitespace
    text = text.strip()

    # Normalize internal whitespace to single spaces
    text = re.sub(r"\s+", " ", text)

    # Remove zero-width characters
    text = re.sub(r"[​-‍﻿]", "", text)

    return text


def truncate_text(text: Optional[str], max_length: int = 500, suffix: str = "...") -> Optional[str]:
    """Hard-cut truncate: first max_length chars, then append suffix.

    Returns None when text is None (not "").

    Parameters
    ----------
    text : str or None
        Text to truncate.
    max_length : int, default 500
        Hard cut point — prefix is exactly max_length characters.
    suffix : str, default "..."
        Suffix appended when truncation occurs.

    Returns
    -------
    str or None
        ``None`` when *text* is ``None``; original *text* when short enough;
        otherwise the first *max_length* characters followed by *suffix*.
    """
    if text is None:
        return None
    if len(text) <= max_length:
        return text
    return text[:max_length] + suffix


def extract_title_from_html(html_str: Optional[str]) -> Optional[str]:
    """Extract the most likely title from raw HTML.

    Tries <h1>, then og:title meta, then <title> (with site-name stripping).

    Parameters
    ----------
    html_str : str or None
        Raw HTML content.

    Returns
    -------
    str or None
        Extracted and cleaned title, or None if not found.
    """
    if not html_str:
        return None

    # Try <h1> first (most likely article title)
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html_str, re.IGNORECASE | re.DOTALL)
    if h1_match:
        title = re.sub(r"<[^>]+>", "", h1_match.group(1))
        title = clean_text(title)
        if title and len(title) > 5:
            return title

    # Try og:title meta tag
    og_match = re.search(
        r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
        html_str,
        re.IGNORECASE,
    )
    if og_match:
        title = clean_text(og_match.group(1))
        if title and len(title) > 5:
            return title

    # Try <title> tag (strip site name suffix like " - Site Name" or " | Site Name")
    title_match = re.search(r"<title>(.*?)</title>", html_str, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = clean_text(title_match.group(1))
        if title is not None:
            title = re.sub(r"\s*[-|&]\s*[^-]+$", "", title).strip()
        else:
            title = title_match.group(1).strip()
        if title and len(title) > 5:
            return title

    return None
