#!/usr/bin/env python3
"""
Baseline Models - Phase 8.

Trains TF-IDF + Logistic Regression and TF-IDF + SVM baseline classifiers,
along with a Vietnamese PhoBERT transformer feature-extraction baseline.
Optimizes hyperparameters using Optuna (5-fold CV) and saves metrics comparison.
"""

import json
import logging
import sys
import hashlib
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.dummy import DummyClassifier
from sklearn.metrics import classification_report, accuracy_score, precision_recall_fscore_support, f1_score
from sklearn.model_selection import StratifiedKFold

# Suppress warnings
warnings.filterwarnings("ignore")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BaselineModels")

TRAIN_PATH = Path("data/final/train.jsonl")
VAL_PATH = Path("data/final/validation.jsonl")
TEST_PATH = Path("data/final/test.jsonl")
RESULTS_PATH = Path("logs/baseline_results.json")
CACHE_PATH = Path("data/final/.phobert_cache.npz")

def load_split(path: Path) -> pd.DataFrame:
    """Loads a split file (.jsonl) into a DataFrame."""
    if not path.exists():
        logger.error(f"Split file not found: {path}")
        sys.exit(1)
    
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return pd.DataFrame(records)

def get_texts_hash(texts: list[str]) -> str:
    """Generates a hash of the texts to validate cache."""
    hasher = hashlib.md5()
    hasher.update(str(len(texts)).encode('utf-8'))
    if len(texts) > 0:
        hasher.update(texts[0].encode('utf-8'))
        hasher.update(texts[-1].encode('utf-8'))
    return hasher.hexdigest()

def tune_logistic_regression(X, y):
    """Tune Logistic Regression C parameter using 5-fold CV and Optuna."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    def objective(trial):
        c = trial.suggest_float("C", 1e-4, 1e2, log=True)
        clf = LogisticRegression(
            C=c,
            class_weight="balanced",
            max_iter=1000,
            random_state=42
        )
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        scores = []
        for train_idx, val_idx in cv.split(X, y):
            X_tr, y_tr = X[train_idx], y[train_idx]
            X_va, y_va = X[val_idx], y[val_idx]
            clf.fit(X_tr, y_tr)
            preds = clf.predict(X_va)
            scores.append(f1_score(y_va, preds, average="macro"))
        return np.mean(scores)
        
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=20)
    return study.best_params

def tune_svm(X, y):
    """Tune LinearSVC C parameter using 5-fold CV and Optuna."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    def objective(trial):
        c = trial.suggest_float("C", 1e-4, 1e2, log=True)
        clf = LinearSVC(
            C=c,
            class_weight="balanced",
            random_state=42,
            max_iter=2000,
            dual="auto"
        )
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        scores = []
        for train_idx, val_idx in cv.split(X, y):
            X_tr, y_tr = X[train_idx], y[train_idx]
            X_va, y_va = X[val_idx], y[val_idx]
            clf.fit(X_tr, y_tr)
            preds = clf.predict(X_va)
            scores.append(f1_score(y_va, preds, average="macro"))
        return np.mean(scores)
        
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=20)
    return study.best_params

def extract_phobert_embeddings(texts, device):
    """Extract PhoBERT embeddings for a list of texts using mean pooling."""
    from pyvi import ViTokenizer
    from transformers import AutoTokenizer, AutoModel
    import torch
    from tqdm import tqdm
    
    logger.info("Loading PhoBERT model and tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
    model = AutoModel.from_pretrained("vinai/phobert-base-v2")
    model = model.to(device)
    model.eval()
    
    batch_size = 32
    embeddings = []
    
    for i in tqdm(range(0, len(texts), batch_size), desc="Extracting PhoBERT embeddings"):
        batch_texts = list(texts[i:i+batch_size])
        # Segment Vietnamese words using pyvi
        segmented = [ViTokenizer.tokenize(t) for t in batch_texts]
        
        inputs = tokenizer(segmented, return_tensors="pt", padding=True, truncation=True, max_length=128)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = model(**inputs)
            # Scaled mean pooling using attention mask
            attention_mask = inputs["attention_mask"].unsqueeze(-1)
            token_embeddings = outputs.last_hidden_state
            masked_embeddings = token_embeddings * attention_mask
            sum_embeddings = masked_embeddings.sum(dim=1)
            sum_mask = attention_mask.sum(dim=1)
            sum_mask = torch.clamp(sum_mask, min=1e-9)
            batch_embeddings = sum_embeddings / sum_mask
            embeddings.append(batch_embeddings.cpu().numpy())
            
    return np.vstack(embeddings)

def evaluate_model(clf, X_train, y_train, X_test, y_test, name):
    """Trains final model, prints report, and returns metrics dict."""
    clf.fit(X_train, y_train)
    preds = clf.predict(X_test)
    
    acc = accuracy_score(y_test, preds)
    prec, rec, f1, _ = precision_recall_fscore_support(y_test, preds, average='binary')
    macro_prec, macro_rec, macro_f1, _ = precision_recall_fscore_support(y_test, preds, average='macro')
    report = classification_report(y_test, preds, output_dict=True)
    
    logger.info(f"\n{name} Classification Report:")
    print(classification_report(y_test, preds, target_names=['non-clickbait', 'clickbait']))
    
    return {
        "accuracy": float(acc),
        "clickbait_class_f1": float(f1),
        "macro_f1": float(macro_f1),
        "report": report
    }

def train_and_evaluate():
    logger.info("=" * 60)
    logger.info("TRAINING BASELINE CLASSIFIERS")
    logger.info("=" * 60)
    
    # 1. Load data
    logger.info("Loading training, validation, and testing datasets...")
    df_train = load_split(TRAIN_PATH)
    df_val = load_split(VAL_PATH)
    df_test = load_split(TEST_PATH)
    
    logger.info(f"Loaded {len(df_train)} training, {len(df_val)} validation, and {len(df_test)} test records.")
    
    # Check for distribution drift
    train_cb_rate = df_train['final_label'].mean()
    val_cb_rate = df_val['final_label'].mean()
    test_cb_rate = df_test['final_label'].mean()
    drift = abs(train_cb_rate - test_cb_rate)
    
    train_cb_count = int((df_train['final_label'] == 1).sum())
    val_cb_count = int((df_val['final_label'] == 1).sum())
    test_cb_count = int((df_test['final_label'] == 1).sum())
    
    logger.info(f"Train size: {len(df_train)} | Train clickbait count: {train_cb_count} ({train_cb_rate:.4f})")
    logger.info(f"Validation size: {len(df_val)} | Validation clickbait count: {val_cb_count} ({val_cb_rate:.4f})")
    logger.info(f"Test size: {len(df_test)} | Test clickbait count: {test_cb_count} ({test_cb_rate:.4f})")
    logger.info(f"Label distribution drift (train vs test): {drift:.4f}")
    
    # Write split stats
    split_stats = {
        "train_size": len(df_train),
        "train_clickbait_count": train_cb_count,
        "train_clickbait_rate": float(train_cb_rate),
        "validation_size": len(df_val),
        "validation_clickbait_count": val_cb_count,
        "validation_clickbait_rate": float(val_cb_rate),
        "test_size": len(df_test),
        "test_clickbait_count": test_cb_count,
        "test_clickbait_rate": float(test_cb_rate),
        "drift": float(drift),
        "drift_warning": bool(drift > 0.05)
    }
    split_stats_path = Path("logs/split_stats.json")
    split_stats_path.parent.mkdir(parents=True, exist_ok=True)
    with open(split_stats_path, "w", encoding="utf-8") as f:
        json.dump(split_stats, f, indent=2, ensure_ascii=False)
    
    # 2. Preprocess
    for df in [df_train, df_test]:
        df["title_clean"] = df["title"].fillna("")
        df["sapo_clean"] = df["sapo"].fillna("")
        df["text_combined"] = df["title_clean"] + " " + df["sapo_clean"]
        df["text_combined"] = df["text_combined"].str.strip()
        
    X_train_text = df_train["text_combined"].values
    X_test_text = df_test["text_combined"].values
    y_train = df_train["final_label"].fillna(0).astype(int).values
    y_test = df_test["final_label"].fillna(0).astype(int).values
    
    if len(set(y_train)) < 2:
        logger.error("Training dataset does not contain at least 2 distinct classes. Cannot train baseline models.")
        return
        
    results = {
        "split_stats": split_stats
    }
    
    # --- Part A: TF-IDF Models ---
    logger.info("\n--- Part A: TF-IDF Baseline ---")
    logger.info("Vectorizing text with TF-IDF...")
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=10000,
        sublinear_tf=True
    )
    X_train_vec = vectorizer.fit_transform(X_train_text)
    X_test_vec = vectorizer.transform(X_test_text)
    
    logger.info("Tuning TF-IDF Logistic Regression hyperparameters...")
    lr_tfidf_params = tune_logistic_regression(X_train_vec, y_train)
    logger.info(f"Best TF-IDF LR params: {lr_tfidf_params}")
    lr_tfidf_model = LogisticRegression(**lr_tfidf_params, class_weight='balanced', max_iter=1000, random_state=42)
    results["logistic_regression"] = evaluate_model(lr_tfidf_model, X_train_vec, y_train, X_test_vec, y_test, "Logistic Regression (TF-IDF, Tuned)")
    
    logger.info("Tuning TF-IDF SVM hyperparameters...")
    svm_tfidf_params = tune_svm(X_train_vec, y_train)
    logger.info(f"Best TF-IDF SVM params: {svm_tfidf_params}")
    svm_tfidf_model = LinearSVC(**svm_tfidf_params, class_weight='balanced', random_state=42, max_iter=2000, dual="auto")
    results["svm"] = evaluate_model(svm_tfidf_model, X_train_vec, y_train, X_test_vec, y_test, "SVM (LinearSVC, TF-IDF, Tuned)")
    
    # --- Part B: PhoBERT Models ---
    logger.info("\n--- Part B: PhoBERT Transformer Baseline ---")
    phobert_success = False
    
    try:
        import torch
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device for PhoBERT: {device}")
        
        train_hash = get_texts_hash(X_train_text)
        test_hash = get_texts_hash(X_test_text)
        
        X_train_emb = None
        X_test_emb = None
        
        # Try loading from cache
        if CACHE_PATH.exists():
            try:
                cache_data = np.load(CACHE_PATH, allow_pickle=True)
                if (cache_data.get("train_hash") == train_hash and 
                    cache_data.get("test_hash") == test_hash):
                    logger.info("Found valid PhoBERT embeddings cache. Loading...")
                    X_train_emb = cache_data["X_train_emb"]
                    X_test_emb = cache_data["X_test_emb"]
                    phobert_success = True
            except Exception as e:
                logger.warning(f"Failed to load PhoBERT cache: {e}. Will re-extract.")
        
        if X_train_emb is None or X_test_emb is None:
            # Extract
            X_train_emb = extract_phobert_embeddings(X_train_text, device)
            X_test_emb = extract_phobert_embeddings(X_test_text, device)
            
            # Save to cache
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                CACHE_PATH,
                X_train_emb=X_train_emb,
                X_test_emb=X_test_emb,
                train_hash=train_hash,
                test_hash=test_hash
            )
            logger.info("PhoBERT embeddings cached successfully.")
            phobert_success = True
            
        if phobert_success:
            logger.info("Tuning PhoBERT Logistic Regression hyperparameters...")
            lr_phobert_params = tune_logistic_regression(X_train_emb, y_train)
            logger.info(f"Best PhoBERT LR params: {lr_phobert_params}")
            lr_phobert_model = LogisticRegression(**lr_phobert_params, class_weight='balanced', max_iter=1000, random_state=42)
            results["logistic_regression_phobert"] = evaluate_model(lr_phobert_model, X_train_emb, y_train, X_test_emb, y_test, "Logistic Regression (PhoBERT, Tuned)")
            
            logger.info("Tuning PhoBERT SVM hyperparameters...")
            svm_phobert_params = tune_svm(X_train_emb, y_train)
            logger.info(f"Best PhoBERT SVM params: {svm_phobert_params}")
            svm_phobert_model = LinearSVC(**svm_phobert_params, class_weight='balanced', random_state=42, max_iter=2000, dual="auto")
            results["svm_phobert"] = evaluate_model(svm_phobert_model, X_train_emb, y_train, X_test_emb, y_test, "SVM (LinearSVC, PhoBERT, Tuned)")
            
            # --- Part B.2: Qualitative Error Analysis for PhoBERT LR ---
            logger.info("Running Qualitative Error Analysis for PhoBERT LR...")
            phobert_preds = lr_phobert_model.predict(X_test_emb)
            fp_indices = np.where((y_test == 0) & (phobert_preds == 1))[0]
            fn_indices = np.where((y_test == 1) & (phobert_preds == 0))[0]
            
            error_analysis = {
                "false_positives": [],
                "false_negatives": []
            }
            for idx in fp_indices[:5]:
                row = df_test.iloc[idx]
                error_analysis["false_positives"].append({
                    "id": str(row.get("id")),
                    "title": str(row.get("title")),
                    "sapo": str(row.get("sapo")),
                    "source": str(row.get("source")),
                    "final_label": 0,
                    "prediction": 1
                })
            for idx in fn_indices[:5]:
                row = df_test.iloc[idx]
                error_analysis["false_negatives"].append({
                    "id": str(row.get("id")),
                    "title": str(row.get("title")),
                    "sapo": str(row.get("sapo")),
                    "source": str(row.get("source")),
                    "final_label": 1,
                    "prediction": 0
                })
            err_path = Path("logs/error_analysis.json")
            err_path.parent.mkdir(parents=True, exist_ok=True)
            with open(err_path, "w", encoding="utf-8") as ef:
                json.dump(error_analysis, ef, indent=2, ensure_ascii=False)
            logger.info(f"Saved qualitative error analysis to {err_path}")
            
    except Exception as e:
        logger.warning(f"Skipping PhoBERT baseline due to error: {e}")
        logger.warning("Only TF-IDF metrics will be saved.")
        
    # --- Part C: Dummy Baseline (Majority Predictor) ---
    logger.info("\n--- Part C: Dummy Baseline ---")
    dummy_model = DummyClassifier(strategy="most_frequent", random_state=42)
    results["dummy"] = evaluate_model(dummy_model, X_train_vec, y_train, X_test_vec, y_test, "Dummy Classifier (Most Frequent)")
        
    # 8. Save results JSON
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Baseline model results saved to {RESULTS_PATH}")
    logger.info("=" * 60)
    logger.info("BASELINE EVALUATION COMPLETED")
    logger.info("=" * 60)

if __name__ == "__main__":
    # Ensure stdout is reconfigured to handle UTF-8 printing on Windows
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    train_and_evaluate()
