import pandas as pd
import yaml
import re
import json
import logging
from pathlib import Path
from typing import List, Tuple, Dict

# Setup logging
log_dir = Path(__file__).resolve().parents[2] / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "exact_dedup.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ExactDeduplicator:
    def __init__(self, config_path: str = "configs/dedup_config.yaml"):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.exact_cfg = self.config.get('exact_dedup', {})
        self.keep_policy = self.config.get('strategy', {}).get('keep_policy', 'latest')

    def normalize_text(self, text: str) -> str:
        """
        Normalize Vietnamese text for exact comparison:
        - Lowercase
        - Remove punctuation
        - Collapse whitespace
        """
        if not text or not isinstance(text, str):
            return ""

        # Lowercase
        text = text.lower()
        # Remove punctuation
        text = re.sub(r'[^\w\s]', ' ', text)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def process(self, input_files: List[Path]) -> Tuple[pd.DataFrame, Dict[str, int]]:
        all_data = []

        # 1. Load data
        for file_path in input_files:
            source = file_path.stem.replace('_validated', '')
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            record = json.loads(line)
                            record['_source_internal'] = source
                            all_data.append(record)
                        except json.JSONDecodeError:
                            logger.warning(f"Malformed JSON line in {file_path}")
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        if not all_data:
            logger.error("No data loaded for deduplication.")
            return pd.DataFrame(), {}

        df = pd.DataFrame(all_data)
        initial_count = len(df)
        logger.info(f"Loaded {initial_count} records for exact deduplication.")

        # 2. Pre-processing & Sorting for Keep Policy
        # Ensure publish_date is datetime for sorting
        df['publish_date'] = pd.to_datetime(df['publish_date'], errors='coerce', utc=True)

        df['body_len'] = df['body_text'].str.len().fillna(0)
        # Sort by body_len descending (longest content first) and publish_date descending (newest second)
        df = df.sort_values(by=['body_len', 'publish_date'], ascending=[False, False])

        # 3. Deduplication Logic
        # We use a mask to track records to keep
        keep_mask = pd.Series(True, index=df.index)

        # A. URL Deduplication
        if self.exact_cfg.get('check_url', True):
            # Use URL as key
            url_dupes = df.duplicated(subset=['url'], keep='first')
            keep_mask &= ~url_dupes
            logger.info(f"URL dedup: removed {url_dupes.sum()} duplicates")

        # B. Canonical URL Deduplication
        if self.exact_cfg.get('check_canonical', True):
            canonical_col = 'canonical_url'
            if canonical_col in df.columns:
                # Only check where canonical exists to avoid dropping NaNs
                canon_mask = df[canonical_col].notna()
                canon_dupes = df[canon_mask].duplicated(subset=[canonical_col], keep='first')
                # Update the main keep_mask for the indices that are duplicates
                keep_mask.loc[canon_dupes[canon_dupes].index] = False
                logger.info(f"Canonical URL dedup: removed {canon_dupes.sum()} duplicates")

        # C. Title Deduplication
        if self.exact_cfg.get('check_title', True):
            df['norm_title'] = df['title'].apply(self.normalize_text)
            df['norm_sapo'] = df['sapo'].apply(self.normalize_text)
            title_dupes = df.duplicated(subset=['norm_title', 'norm_sapo'], keep='first')
            keep_mask &= ~title_dupes
            logger.info(f"Title+Sapo exact dedup: removed {title_dupes.sum()} duplicates")
            df = df.drop(columns=['norm_title', 'norm_sapo'])

        # 4. Final Filtering
        df_final = df[keep_mask].copy()
        # Cast explicitly to DataFrame to satisfy Pyright
        df_final = pd.DataFrame(df_final)

        # Remove temporary columns
        if 'body_len' in df_final.columns:
            df_final = df_final.drop(columns=['body_len'])
        if '_source_internal' in df_final.columns:
            df_final = df_final.drop(columns=['_source_internal'])

        # 5. Calculate removed per source
        removed_df = df[~keep_mask]
        removed_per_source = removed_df['_source_internal'].value_counts().to_dict()

        logger.info(f"Exact dedup complete. Initial: {initial_count}, Final: {len(df_final)}")
        logger.info(f"Total removed: {initial_count - len(df_final)}")
        logger.info(f"Removed per source: {removed_per_source}")

        return df_final, removed_per_source

if __name__ == "__main__":
    # This block allows running the script standalone for testing
    from pathlib import Path

    deduper = ExactDeduplicator()
    validated_dir = Path("data/validated")
    input_files = list(validated_dir.glob("*.jsonl"))

    if not input_files:
        logger.error("No validated files found in data/validated/")
    else:
        df_result, stats = deduper.process(input_files)

        # Save result to intermediate file for semantic dedup
        output_dir = Path("data/dedup")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / "exact_deduped.jsonl"
        df_result.to_json(output_file, orient='records', lines=True, force_ascii=False)
        logger.info(f"Saved exact deduped results to {output_file}")
