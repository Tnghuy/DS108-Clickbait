import os
import json
import logging
import requests
import re
import time
from typing import Dict, Any, Optional, Tuple
from tqdm import tqdm

import trafilatura
from bs4 import BeautifulSoup
from ftfy import fix_text

from src.validation.url_filter import should_keep_url
from src.utils.text_cleaner import clean_text, extract_title_from_html

# Configure logging
from pathlib import Path
log_dir = Path(__file__).resolve().parents[2] / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'extraction_errors.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Custom selectors common in Vietnamese news sites to act as a fallback for trafilatura
CUSTOM_SELECTORS = [
    '.detail-content', '.article-content', '.entry-content', '.content-detail',
    '.main-content', '.post-content', '.text-content', '.article-body',
    'div[itemprop="articleBody"]', 'section.article-body'
]

# Custom selectors for Sapo/Description in major Vietnamese newspapers
SAPO_SELECTORS = [
    'h2.sapo', 'div.sapo', 'p.sapo', '.sapo',
    '.description', 'p.description', '.lead',
    '.detail-sapo', '.sapo-content', '.kl-sapo',
    '#sapo', '.sapo-detail'
]

def clean_sapo(sapo: Optional[str]) -> Optional[str]:
    """
    Cleans Sapo text by stripping HTML and removing common noise patterns.
    """
    if not sapo:
        return None
    soup = BeautifulSoup(sapo, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    text = re.sub(r'https?://\S+\.(?:jpg|jpeg|png|gif|webp|avif)\S*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'(?i)(xem thêm|đọc thêm|click để xem chi tiết|tiếp tục đọc)', '', text)
    text = re.sub(r'@\w+', '', text)
    return clean_text(text)

def clean_boilerplate(text: Optional[str], source: str) -> Optional[str]:
    """
    Removes source-specific boilerplate from body text.
    """
    if not text:
        return None
    boilerplate_patterns = [
        r'(?i)vui lòng đăng ký nhận bản tin.*',
        r'(?i)theo dõi chúng tôi trên.*',
        r'(?i)bản quyền thuộc về.*',
    ]
    source_patterns = {
        'nhandan': [
            r'(?i)Chúng tôi xin thông báo để các cơ quan, đoàn thể, đơn vị, trường học và bạn đọc đặt mua các ấn phẩm Báo Nhân Dân.*',
            r'(?i)Đường dây nóng: \(84\) 24 393 82413.*',
            r'(?i)Xin trân trọng cảm ơn!',
            r'(?i)Truy cập nhandan.vn để xem thêm chi tiết.*',
        ],
        'kenh14': [
            r'(?i)Xem thêm các bài viết cùng chủ đề.*',
        ]
    }
    current_patterns = boilerplate_patterns + source_patterns.get(source, [])
    for pattern in current_patterns:
        text = re.sub(pattern, '', text)
    return clean_text(text)

class ArticleExtractor:
    def __init__(self, timeout: int = 15, user_agent: Optional[str] = None):
        self.timeout = timeout
        self.headers = {
            'User-Agent': user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def fetch_html(self, url: str) -> Optional[str]:
        """Fetches raw HTML from a URL with categorized error handling."""
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return fix_text(response.text)
        except requests.Timeout:
            logger.warning(f"Timeout fetching {url}.")
        except requests.HTTPError as e:
            logger.error(f"HTTP {e.response.status_code} fetching {url}.")
        except requests.RequestException as e:
            logger.error(f"Request error fetching {url}: {e}.")
        return None

    def extract_content(self, html: str, url: str) -> Dict[str, Any]:
        """Tiered extraction pipeline."""
        result = {"body": None, "title": None, "sapo": None}
        soup = BeautifulSoup(html, 'html.parser')
        
        # Use centralized robust title extraction
        result["title"] = extract_title_from_html(html)

        # Extract Sapo
        for selector in SAPO_SELECTORS:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(separator=' ', strip=True)
                if len(text) > 30:
                    result["sapo"] = text
                    break

        # Fallback for Sapo: first paragraph in body text that has sufficient length
        if not result["sapo"]:
            paragraphs = soup.find_all('p')
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 40:
                    result["sapo"] = text
                    break

        extracted_body = trafilatura.extract(html, include_comments=False, include_tables=False)
        if extracted_body and len(extracted_body.strip()) > 200:
            result["body"] = extracted_body
        else:
            for selector in CUSTOM_SELECTORS:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text(separator=' ', strip=True)
                    if len(text) > 200:
                        result["body"] = text
                        break
            if not result["body"]:
                paragraphs = soup.find_all('p')
                text = ' '.join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
                if len(text) > 200:
                    result["body"] = text
        return result

    def process_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Full pipeline for a single record. Returns a new dict to avoid mutating original."""
        url = record.get('url')
        if not isinstance(url, str) or not should_keep_url(url):
            return None

        html = self.fetch_html(url)
        if not html:
            return None

        extraction_result = self.extract_content(html, url)
        raw_body = extraction_result.get("body")
        extracted_title = extraction_result.get("title")
        extracted_sapo = extraction_result.get("sapo")

        if not raw_body:
            return None

        source_name = record.get('source', 'unknown')
        cleaned_body = clean_boilerplate(raw_body, source_name)

        if not cleaned_body or len(cleaned_body) < 150:
            return None

        # Create a shallow copy to avoid mutating the original record
        output = {**record}

        # Title fallback
        output['title'] = (record.get('title') or extracted_title) or None

        # Sapo fallback and cleaning
        # Prioritize the sapo extracted from HTML, fallback to the raw 'sapo' (which was snippet in raw records)
        raw_sapo = extracted_sapo or record.get('sapo') or record.get('snippet')
        output['sapo'] = clean_sapo(raw_sapo) if raw_sapo else clean_sapo(cleaned_body[:200])

        # Remove old snippet field to keep the schema clean
        if 'snippet' in output:
            del output['snippet']

        output['body_text'] = cleaned_body
        output['body_preview'] = cleaned_body[:500] + ("..." if len(cleaned_body) > 500 else "")
        output['extraction_success'] = True

        return output

    def process_source(self, source_name: str):
        """Processes a single source file from raw to filtered using concurrency."""
        input_path = f'data/raw/{source_name}_raw.jsonl'
        output_path = f'data/filtered/{source_name}_filtered.jsonl'

        if not os.path.exists(input_path):
            logger.warning(f"Source file not found: {input_path}")
            return

        processed_ids = set()
        if os.path.exists(output_path):
            with open(output_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        processed_ids.add(json.loads(line)['id'])
                    except (json.JSONDecodeError, KeyError) as e:
                        continue

        records_to_process = []
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    record = json.loads(line)
                    if record.get('id') not in processed_ids:
                        records_to_process.append(record)
                except json.JSONDecodeError:
                    continue

        remaining = len(records_to_process)
        logger.info(f"Starting concurrent extraction for {source_name}. Total raw: {len(processed_ids) + remaining}, Already processed: {len(processed_ids)}, Remaining: {remaining}")

        if remaining == 0:
            return

        import concurrent.futures
        import threading
        
        # Thread-safe stats and writing
        write_lock = threading.Lock()
        success_count = 0
        stats = {"rejected_url": 0, "fetch_failed": 0, "extract_failed": 0, "success": 0}

        def worker(record):
            nonlocal success_count
            url = record.get('url', '')
            
            if not should_keep_url(url):
                with write_lock:
                    stats["rejected_url"] += 1
                return None
                
            # Politeness delay per thread
            time.sleep(0.1)
            
            result = self.process_record(record)
            with write_lock:
                if result:
                    from src.utils.schema import FilteredRecord, validate_record
                    if "publish_date" in result and isinstance(result["publish_date"], float):
                        result["publish_date"] = None
                    if validate_record(result, FilteredRecord):
                        stats["success"] += 1
                        success_count += 1
                        with open(output_path, 'a', encoding='utf-8') as fout:
                            fout.write(json.dumps(result, ensure_ascii=False) + '\n')
                    else:
                        stats["extract_failed"] += 1
                        logger.warning(f"Skipping record {result.get('id')} due to FilteredRecord schema failure.")
                else:
                    stats["fetch_failed"] += 1
            return result

        max_workers = 8
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor, \
             tqdm(total=remaining, desc=f"[{source_name}]", unit="record") as pbar:
             
            futures = {executor.submit(worker, rec): rec for rec in records_to_process}
            
            for future in concurrent.futures.as_completed(futures):
                pbar.update(1)

        rate = success_count / len(records_to_process) if len(records_to_process) > 0 else 0
        logger.info(f"Finished concurrent extraction for {source_name}. Success: {success_count}, Rate: {rate:.2%}")
        logger.info(f"Detailed Stats for {source_name}: {stats}")

    def main(self):
        os.makedirs('data/filtered', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        raw_files = [f for f in os.listdir('data/raw') if f.endswith('_raw.jsonl')]
        sources = [f.replace('_raw.jsonl', '') for f in raw_files]
        for source in sources:
            self.process_source(source)

if __name__ == "__main__":
    extractor = ArticleExtractor()
    extractor.main()
