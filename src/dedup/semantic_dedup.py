import json
import logging
import yaml
import re
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

# Setup logging
log_dir = Path(__file__).resolve().parents[2] / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "semantic_dedup.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SemanticDeduplicator:
    def __init__(self, config_path: str = "configs/dedup_config.yaml"):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.sem_cfg = self.config.get('semantic_dedup', {})
        self.thresholds = self.config.get('thresholds', {})
        self.strategy = self.config.get('strategy', {})
        self.keep_policy = self.strategy.get('keep_policy', 'latest')

        # Hardware Constraint: Force CPU to save VRAM for annotation
        self.model_name = self.config.get('model_name', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        logger.info(f"Loading model {self.model_name} on CPU...")
        self.model = SentenceTransformer(self.model_name, device='cpu')

        self.cache_dir = Path(self.config.get('embeddings_cache_dir', '.embeddings_cache'))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_sentence_structure_penalty(self, s1: str, s2: str) -> float:
        """
        Calculate penalty coefficient based on sentence structure:
        1. Length ratio penalty: if len_max / len_min > 1.5, penalty = 0.8
        2. Ending punctuation penalty: if ending punctuation type differs, penalty = 0.9
        """
        s1 = str(s1 or '').strip()
        s2 = str(s2 or '').strip()
        if not s1 or not s2:
            return 1.0

        penalty = 1.0
        
        # 1. Length Ratio Check
        l1, l2 = len(s1), len(s2)
        if min(l1, l2) > 0:
            ratio = max(l1, l2) / min(l1, l2)
            if ratio > 1.5:
                penalty *= 0.8

        # 2. Ending Punctuation Check (e.g. ? vs . or !)
        punc1 = s1[-1] if s1[-1] in "?!" else ""
        punc2 = s2[-1] if s2[-1] in "?!" else ""
        
        # Simplify to: does one end with question mark and the other not?
        is_q1 = s1.endswith('?')
        is_q2 = s2.endswith('?')
        if is_q1 != is_q2:
            penalty *= 0.9

        return penalty

    def _get_embeddings(self, records: List[Dict[str, Any]], field_name: str) -> np.ndarray:
        """
        Generate embeddings for a specific field (title or sapo) with batching and .npz caching.
        """
        cache_enabled = self.config.get('cache_embeddings', True)
        cache_file = self.cache_dir / f"embeddings_{field_name}_cache.npz"
        
        cached_dict = {}
        if cache_enabled and cache_file.exists():
            try:
                with np.load(cache_file, allow_pickle=True) as data:
                    cached_dict = {k: data[k] for k in data.files}
                logger.info(f"Loaded {len(cached_dict)} cached {field_name} embeddings from {cache_file}")
            except Exception as e:
                logger.warning(f"Error loading {field_name} embedding cache: {e}")

        embeddings = np.zeros((len(records), self.config.get('embedding_dim', 384)), dtype=np.float32)
        to_generate_indices = []
        to_generate_texts = []

        for idx, r in enumerate(records):
            rid = r.get('id')
            if cache_enabled and rid in cached_dict:
                embeddings[idx] = cached_dict[rid]
            else:
                to_generate_indices.append(idx)
                to_generate_texts.append(str(r.get(field_name) or '').strip())

        if to_generate_texts:
            batch_size = self.config.get('embedding_batch_size', 32)
            logger.info(f"Generating {field_name} embeddings for {len(to_generate_texts)} / {len(records)} records...")
            new_embs = self.model.encode(
                to_generate_texts,
                batch_size=batch_size,
                show_progress_bar=True,
                normalize_embeddings=self.sem_cfg.get('normalize_embeddings', True)
            )
            for idx, gen_idx in enumerate(to_generate_indices):
                embeddings[gen_idx] = new_embs[idx]

            # Save updated cache
            if cache_enabled:
                for idx, gen_idx in enumerate(to_generate_indices):
                    rid = records[gen_idx].get('id')
                    if rid:
                        cached_dict[rid] = new_embs[idx]
                try:
                    np.savez(cache_file, **cached_dict)
                    logger.info(f"Saved updated {field_name} cache with {len(cached_dict)} records to {cache_file}")
                except Exception as e:
                    logger.warning(f"Error saving {field_name} embedding cache: {e}")

        return embeddings

    def process(self, input_path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        if not input_path.exists():
            logger.error(f"Input file {input_path} not found.")
            return pd.DataFrame(), {}

        # 1. Load data
        records = []
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if not records:
            logger.error("No records loaded for semantic deduplication.")
            return pd.DataFrame(), {}

        df = pd.DataFrame(records)
        initial_count = len(df)
        logger.info(f"Loaded {initial_count} records for semantic deduplication.")

        df['body_len'] = df['body_text'].str.len().fillna(0)
        # Sort by body_len descending (longest content first) and publish_date descending (newest second)
        df = df.sort_values(by=['body_len', 'publish_date'], ascending=[False, False]).reset_index(drop=True)
        sorted_records = df.to_dict(orient='records')

        # 3. Fit TF-IDF Vectorizers for Lexical Similarity
        logger.info("Computing TF-IDF vectorizers...")
        title_vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        sapo_vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        
        titles = [str(r.get('title') or '').strip() for r in sorted_records]
        sapos = [str(r.get('sapo') or '').strip() for r in sorted_records]
        
        title_tfidf = title_vectorizer.fit_transform(titles)
        sapo_tfidf = sapo_vectorizer.fit_transform(sapos)

        # 4. Generate Semantic Embeddings
        logger.info("Retrieving Title and Sapo semantic embeddings...")
        title_embs = self._get_embeddings(sorted_records, "title")
        sapo_embs = self._get_embeddings(sorted_records, "sapo")

        # Ensure L2 normalized semantic embeddings for exact dot product cosine similarity
        logger.info("Normalizing semantic embeddings...")
        title_norms = np.linalg.norm(title_embs, axis=1, keepdims=True)
        title_norms[title_norms == 0] = 1.0
        title_embs_norm = title_embs / title_norms

        sapo_norms = np.linalg.norm(sapo_embs, axis=1, keepdims=True)
        sapo_norms[sapo_norms == 0] = 1.0
        sapo_embs_norm = sapo_embs / sapo_norms

        # Precompute sparse lexical similarity matrices to avoid N sparse matrix multiplications in loop
        logger.info("Precomputing lexical similarity sparse matrices...")
        sim_title_lex_sparse = title_tfidf @ title_tfidf.T
        sim_sapo_lex_sparse = sapo_tfidf @ sapo_tfidf.T

        # 5. Hybrid Similarity Analysis with Decomposed Gate & Sentence Structure Penalty
        keep_mask = np.ones(len(df), dtype=bool)
        dup_pairs = []
        stats = {"auto_removed": 0, "probable_dup": 0, "review_candidate": 0}

        t_auto = self.thresholds.get('auto_remove', 0.97)
        t_prob = self.thresholds.get('probable_dup', 0.92)
        t_rev = self.thresholds.get('review_candidate', 0.85)

        logger.info("Analyzing similarities using Decomposed Hybrid Gate...")
        import time
        t_start = time.time()
        total_items = len(df)
        total_work = total_items * (total_items - 1) / 2
        
        # Compare all pairs (n^2 / 2)
        for i in range(total_items):
            if i % 1000 == 0 and i > 0:
                elapsed = time.time() - t_start
                percent = (i / total_items) * 100
                work_done = i * (total_items - 1) - i * (i - 1) / 2
                frac = work_done / total_work if total_work > 0 else 1.0
                eta = (elapsed / frac) - elapsed if frac > 0 else 0
                logger.info(f"Progress: {i}/{total_items} articles ({percent:.1f}% items, {frac*100:.1f}% comparison work done) | Elapsed: {elapsed:.1f}s | ETA: {eta:.1f}s")

            if not keep_mask[i]:
                continue

            if i == total_items - 1:
                break

            # Compute row i similarities on-the-fly to prevent memory overflow (1.4+ GiB arrays)
            sim_title_sem = np.dot(title_embs_norm[i+1:], title_embs_norm[i])
            sim_sapo_sem = np.dot(sapo_embs_norm[i+1:], sapo_embs_norm[i])
            
            # Slice precomputed sparse matrices for lexical similarity
            sim_title_lex = sim_title_lex_sparse[i, i+1:].toarray().flatten()
            sim_sapo_lex = sim_sapo_lex_sparse[i, i+1:].toarray().flatten()
            
            score_title_base = 0.7 * sim_title_sem + 0.3 * sim_title_lex
            score_sapo_base = 0.7 * sim_sapo_sem + 0.3 * sim_sapo_lex

            title_i = df.iloc[i]['title']
            sapo_i = df.iloc[i]['sapo']

            for idx_offset, j in enumerate(range(i + 1, total_items)):
                if not keep_mask[j]:
                    continue

                # Fast pre-filtering
                if score_title_base[idx_offset] < 0.90:
                    continue

                title_j = df.iloc[j]['title']
                sapo_j = df.iloc[j]['sapo']

                # 5.3 Sentence Structure Penalties
                penalty_title = self._get_sentence_structure_penalty(title_i, title_j)
                penalty_sapo = self._get_sentence_structure_penalty(sapo_i, sapo_j)

                # 5.4 Hybrid Score (0.7 * Sem + 0.3 * Lex) * Penalty
                score_title = score_title_base[idx_offset] * penalty_title
                score_sapo = score_sapo_base[idx_offset] * penalty_sapo

                # 5.5 Decomposed Gate logic
                # Rule A: Same title but completely different content/sapo -> Keep both (no dedup)
                if score_title >= 0.95 and score_sapo < 0.75:
                    continue

                # Rule B: Only dedup if both title and sapo similarities are above critical thresholds
                if score_title >= 0.90 and score_sapo >= 0.85:
                    # Calculate joint score for thresholding
                    joint_score = 0.6 * score_title + 0.4 * score_sapo

                    if joint_score >= t_auto:
                        keep_mask[j] = False
                        stats["auto_removed"] += 1
                        dup_pairs.append({
                            "keep_id": df.iloc[i]['id'],
                            "remove_id": df.iloc[j]['id'],
                            "similarity": float(joint_score),
                            "action": "auto_remove"
                        })
                    elif t_prob <= joint_score < t_auto:
                        stats["probable_dup"] += 1
                        dup_pairs.append({
                            "keep_id": df.iloc[i]['id'],
                            "remove_id": df.iloc[j]['id'],
                            "similarity": float(joint_score),
                            "action": "probable_dup"
                        })
                    elif t_rev <= joint_score < t_prob:
                        stats["review_candidate"] += 1
                        dup_pairs.append({
                            "keep_id": df.iloc[i]['id'],
                            "remove_id": df.iloc[j]['id'],
                            "similarity": float(joint_score),
                            "action": "review_candidate"
                        })

        # 6. Final Filtering
        df_final = df[keep_mask].copy()

        if self.config.get('save_duplicate_pairs', True):
            audit_file = Path("logs/semantic_dup_pairs.jsonl")
            audit_file.parent.mkdir(parents=True, exist_ok=True)
            with open(audit_file, 'w', encoding='utf-8') as f:
                for pair in dup_pairs:
                    f.write(json.dumps(pair, ensure_ascii=False) + "\n")
            logger.info(f"Saved {len(dup_pairs)} duplicate pairs to {audit_file}")

        logger.info(f"Semantic dedup complete. Initial: {initial_count}, Final: {len(df_final)}")
        logger.info(f"Stats: {stats}")

        return df_final, stats

if __name__ == "__main__":
    deduper = SemanticDeduplicator()
    input_file = Path("data/dedup/exact_deduped.jsonl")

    if not input_file.exists():
        logger.error(f"Input file {input_file} not found. Run exact_deduplicator.py first.")
    else:
        df_result, stats = deduper.process(input_file)
        output_file = Path("data/dedup/final_deduped.jsonl")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df_result.to_json(output_file, orient='records', lines=True, force_ascii=False)
        logger.info(f"Saved semantic deduped results to {output_file}")
