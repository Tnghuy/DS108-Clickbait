import json
import os
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
import yaml
from tqdm import tqdm

# --- Configuration ---
INPUT_DIR = Path("data/filtered")
OUTPUT_DIR = Path("data/validated")
LOG_DIR = Path("logs")
REJECTED_LOG = LOG_DIR / "quality_rejected.jsonl"

# Load quality threshold dynamically from config based on APP_ENV
import os
env = os.environ.get("APP_ENV", "dev")
config_path = Path(f"configs/pipeline_config.{env}.yaml")
if not config_path.exists():
    config_path = Path("configs/pipeline_config.yaml")

if config_path.exists():
    with open(config_path, "r", encoding="utf-8") as f:
        pipeline_config = yaml.safe_load(f)
    QUALITY_THRESHOLD = pipeline_config.get("quality_threshold", 4)
else:
    QUALITY_THRESHOLD = 4

# Blacklist for generic titles (Aggregation/System pages)
TITLE_BLACKLIST = {
    "home", "search", "results", "loading", "category",
    "tag", "archive", "page", "index", "trang chủ",
    "kết quả tìm kiếm", "danh mục", "thẻ"
}

# Setup logging
LOG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "quality_scoring.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class QualityScorer:
    """
    Implements the quality rubric for Vietnamese articles.
    Scores articles from 0 to 6 based on content integrity.
    """

    def __init__(self, threshold: int = QUALITY_THRESHOLD):
        self.threshold = threshold

    def _ensure_str(self, value: Any) -> str:
        """Helper to ensure value is a string and not None."""
        return str(value) if value is not None else ""

    def check_valid_title(self, title: str) -> bool:
        title = self._ensure_str(title)
        if not title or not title.strip():
            return False
        clean_title = title.strip().lower()
        if len(clean_title) < 5:
            return False
        if any(word in clean_title for word in TITLE_BLACKLIST):
            return False
        return True

    def check_valid_sapo(self, title: str, sapo: str) -> bool:
        title = self._ensure_str(title)
        sapo = self._ensure_str(sapo)
        if not sapo or not sapo.strip():
            return False
        if len(sapo.strip()) < 30:
            return False
        if title.strip().lower() == sapo.strip().lower():
            return False
        return True

    def check_valid_body_preview(self, body: str) -> bool:
        body = self._ensure_str(body)
        if not body or not body.strip():
            return False
        if len(body.strip()) < 200:
            return False
        return True

    def check_sufficient_length(self, body: str) -> bool:
        body = self._ensure_str(body)
        if not body:
            return False
        return len(body.strip()) >= 500

    def check_non_aggregation(self, body: str) -> bool:
        body = self._ensure_str(body)
        if not body:
            return False
        preview = body[:1000]
        links = re.findall(r'https?://\S+', preview)
        return len(links) <= 5

    def check_low_repetition(self, body: str) -> bool:
        body = self._ensure_str(body)
        if not body:
            return False
        words = body.lower().split()
        if not words:
            return False
        # Limit to the first 200 words to mitigate length bias from Zipf's law
        words = words[:200]
        unique_words = set(words)
        ttr = len(unique_words) / len(words)
        return ttr >= 0.4

    def score_article(self, record: Dict[str, Any]) -> Tuple[int, Dict[str, bool]]:
        title = record.get("title")
        sapo = record.get("sapo")
        body = record.get("body_preview") or record.get("body")

        breakdown = {
            "valid_title": self.check_valid_title(title),
            "valid_sapo": self.check_valid_sapo(title, sapo),
            "valid_body_preview": self.check_valid_body_preview(body),
            "sufficient_length": self.check_sufficient_length(body),
            "non_aggregation": self.check_non_aggregation(body),
            "low_repetition": self.check_low_repetition(body),
        }

        score = sum(breakdown.values())
        if not breakdown["valid_title"] or not breakdown["valid_sapo"]:
            score = 0
        return score, breakdown

    def process_source(self, source_name: str):
        input_file = INPUT_DIR / f"{source_name}.jsonl"
        if not input_file.exists():
            input_file = INPUT_DIR / f"{source_name}_filtered.jsonl"

        output_file = OUTPUT_DIR / f"{source_name}_validated.jsonl"

        if not input_file.exists():
            logger.warning(f"Input file not found for source {source_name}: {input_file}")
            return

        logger.info(f"Processing source: {source_name}...")

        passed_count = 0
        total_count = 0

        # Clear existing output file for this source to avoid duplicates if rerunning
        if output_file.exists():
            output_file.unlink()

        with open(input_file, 'r', encoding='utf-8') as fin, \
             open(output_file, 'w', encoding='utf-8') as fout, \
             open(REJECTED_LOG, 'a', encoding='utf-8') as f_reject:

            for line in tqdm(fin, desc=f"Scoring {source_name}"):
                try:
                    record = json.loads(line)
                    total_count += 1

                    score, breakdown = self.score_article(record)
                    record["quality_score"] = score
                    record["quality_breakdown"] = breakdown

                    if score >= self.threshold:
                        from src.utils.schema import ValidatedRecord, validate_record
                        if "publish_date" in record and isinstance(record["publish_date"], float):
                            record["publish_date"] = None
                        if validate_record(record, ValidatedRecord):
                            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                            passed_count += 1
                        else:
                            logger.warning(f"Skipping record {record.get('id')} in {source_name} due to ValidatedRecord schema failure.")
                            f_reject.write(json.dumps(record, ensure_ascii=False) + "\n")
                    else:
                        f_reject.write(json.dumps(record, ensure_ascii=False) + "\n")

                except Exception as e:
                    logger.error(f"Error processing record in {source_name}: {e}")

        survival_rate = (passed_count / total_count * 100) if total_count > 0 else 0
        logger.info(f"Source {source_name}: {passed_count}/{total_count} passed. Survival Rate: {survival_rate:.2f}%")

def main():
    scorer = QualityScorer()

    all_files = list(INPUT_DIR.glob("*.jsonl"))
    source_files = [f for f in all_files if "_validated" not in f.name and "_quality_passed" not in f.name]

    if not source_files:
        logger.error("No valid source .jsonl files found in data/filtered/")
        return

    logger.info(f"Found {len(source_files)} source files to score.")

    for src_file in source_files:
        source_name = src_file.stem.replace("_filtered", "")
        scorer.process_source(source_name)

    logger.info("Quality scoring completed successfully. Outputs are in data/validated/")

if __name__ == "__main__":
    main()
