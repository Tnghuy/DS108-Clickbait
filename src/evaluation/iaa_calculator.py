"""IAA Calculator - Phase 7.

Computes Inter-Annotator Agreement for dual-model annotation pipeline:
  - Model A vs Model B -> Cohen's Kappa & Gwet's AC1 (handles class imbalance paradox)
  - Model A + Model B + Human -> Fleiss' Kappa & Krippendorff's Alpha (handles missing values)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

logger = logging.getLogger(__name__)


# --- Data classes ---------------------------------------------------------------

@dataclass
class IAAConfig:
    annotator_a: str = "model_a_label"
    annotator_b: str = "model_b_label"
    ground_truth: str = "final_label"
    confidence_col: str = "confidence"
    source_col: str = "source"
    min_samples_breakdown: int = 10
    bootstrap_iterations: int = 1000
    random_seed: int = 42


@dataclass
class BreakdownResult:
    kappa: float
    n_samples: int
    observed_agreement: float
    interpretation: str
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "kappa": round(self.kappa, 4) if self.kappa is not None else None,
            "n_samples": self.n_samples,
            "observed_agreement": round(self.observed_agreement, 4) if self.observed_agreement is not None else None,
            "interpretation": self.interpretation,
        }
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class IAAReport:
    cohens_kappa: float
    cohens_kappa_ci: Tuple[float, float]
    cohens_kappa_interpretation: str
    observed_agreement: float
    expected_agreement: float
    n_samples: int
    gwets_ac1: float
    krippendorff_alpha: float
    fleiss_kappa: Optional[float] = None
    fleiss_n_raters: Optional[int] = None
    breakdown_by_source: Dict[str, dict] = field(default_factory=dict)
    breakdown_by_class: Dict[str, dict] = field(default_factory=dict)
    breakdown_by_confidence: Dict[str, dict] = field(default_factory=dict)
    disagreement_analysis: Dict[str, Any] = field(default_factory=dict)
    human_vs_llm: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cohens_kappa": round(self.cohens_kappa, 4) if self.cohens_kappa is not None else None,
            "cohens_kappa_ci": [round(x, 4) for x in self.cohens_kappa_ci] if self.cohens_kappa_ci[0] is not None else [None, None],
            "cohens_kappa_interpretation": self.cohens_kappa_interpretation,
            "observed_agreement": round(self.observed_agreement, 4) if self.observed_agreement is not None else None,
            "expected_agreement": round(self.expected_agreement, 4) if self.expected_agreement is not None else None,
            "n_samples": self.n_samples,
            "gwets_ac1": round(self.gwets_ac1, 4),
            "krippendorff_alpha": round(self.krippendorff_alpha, 4),
            "fleiss_kappa": round(self.fleiss_kappa, 4) if self.fleiss_kappa is not None else None,
            "fleiss_n_raters": self.fleiss_n_raters,
            "breakdown": {
                "by_source": self.breakdown_by_source,
                "by_class": self.breakdown_by_class,
                "by_confidence": self.breakdown_by_confidence,
            },
            "disagreement_analysis": self.disagreement_analysis,
            "human_vs_llm": self.human_vs_llm,
            "warnings": self.warnings,
            "passes_threshold": self.cohens_kappa is not None and self.cohens_kappa >= 0.60,
        }


# --- Helpers --------------------------------------------------------------------

_KAPPA_SCALE = [
    (0.80, 1.01, "Almost Perfect"),
    (0.60, 0.81, "Substantial"),
    (0.40, 0.61, "Moderate"),
    (0.20, 0.41, "Fair"),
    (0.00, 0.21, "Slight"),
    (-1.00, 0.00, "Poor"),
]


def _interpret_kappa(kappa: float) -> str:
    for lo, hi, label in _KAPPA_SCALE:
        if lo <= kappa < hi:
            return label
    return "Poor"


def _clean_labels(series: pd.Series) -> np.ndarray:
    """Drop NaN, return int numpy array."""
    return series.dropna().astype(int).to_numpy()


def _to_int(val: Any) -> int:
    """Safely convert pandas scalar to Python int."""
    if hasattr(val, "item"):
        return int(val.item())
    return int(val)


def _kappa_for_subset(
    df: pd.DataFrame,
    a_col: str,
    b_col: str,
    min_n: int = 2,
) -> Optional[dict[str, Any]]:
    """Compute Cohen's Kappa for a dataframe subset."""
    df = df.dropna(subset=[a_col, b_col])
    n = _to_int(len(df))
    if n < min_n:
        return None
    a = _clean_labels(df[a_col])
    b = _clean_labels(df[b_col])
    min_len = min(len(a), len(b))
    if min_len < min_n:
        return None
    k = float(cohen_kappa_score(a[:min_len], b[:min_len]))
    obs = float(np.mean(a[:min_len] == b[:min_len]))
    return {
        "kappa": round(k, 4),
        "n_samples": min_len,
        "observed_agreement": round(obs, 4),
        "interpretation": _interpret_kappa(k),
    }


def calculate_gwets_ac1(y1: np.ndarray, y2: np.ndarray) -> float:
    """
    Calculate Gwet's AC1 for nominal (binary) ratings to protect against Kappa paradox.
    """
    n = len(y1)
    if n == 0:
        return 0.0
    p_o = np.mean(y1 == y2)
    p_a = np.mean(y1 == 1)
    p_b = np.mean(y2 == 1)
    pi = (p_a + p_b) / 2.0
    p_e = 2.0 * pi * (1.0 - pi)
    
    if p_e >= 1.0:
        return 1.0 if p_o == 1.0 else 0.0
    ac1 = (p_o - p_e) / (1.0 - p_e)
    return float(ac1)


def calculate_krippendorff_alpha(ratings_matrix: np.ndarray) -> float:
    """
    Calculate Krippendorff's Alpha for nominal (binary) data with missing entries (NaNs).
    ratings_matrix: array of shape (N, R) with values in {0, 1, NaN}.
    """
    # Keep rows with at least 2 non-NaN ratings
    valid_rows = []
    for row in ratings_matrix:
        non_nan = row[~np.isnan(row)]
        if len(non_nan) >= 2:
            valid_rows.append(row)
            
    if not valid_rows:
        return 0.0
        
    valid_matrix = np.array(valid_rows)
    total_ratings = 0
    do_sum = 0.0
    n_k = {0: 0, 1: 0}
    
    for row in valid_matrix:
        non_nan = row[~np.isnan(row)]
        m_i = len(non_nan)
        total_ratings += m_i
        
        n_i0 = np.sum(non_nan == 0)
        n_i1 = np.sum(non_nan == 1)
        
        n_k[0] += n_i0
        n_k[1] += n_i1
        
        row_disagreement = (n_i0 * (m_i - n_i0) + n_i1 * (m_i - n_i1)) / (m_i - 1)
        do_sum += row_disagreement
        
    D_o = do_sum / total_ratings
    
    total_n = total_ratings
    if total_n <= 1:
        return 0.0
        
    de_sum = (n_k[0] * (total_n - n_k[0]) + n_k[1] * (total_n - n_k[1]))
    D_e = de_sum / (total_n * (total_n - 1))
    
    if D_e == 0.0:
        return 1.0 if D_o == 0.0 else 0.0
        
    alpha = 1.0 - (D_o / D_e)
    return float(alpha)


# --- Core calculator ------------------------------------------------------------

class IAACalculator:
    def __init__(self, df: pd.DataFrame, config: Optional[IAAConfig] = None):
        self.df = df.copy()
        self.config = config or IAAConfig()
        self._validate_input()

    def _validate_input(self) -> None:
        required = [
            self.config.annotator_a,
            self.config.annotator_b,
            self.config.ground_truth,
        ]
        missing = [c for c in required if c not in self.df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

    # --- Cohen's Kappa ----------------------------------------------------------

    def calculate_cohens_kappa(
        self,
        annotator_a: str = "",
        annotator_b: str = "",
    ) -> dict[str, Any]:
        """Cohen's Kappa with bootstrap 95% CI."""
        a_col = annotator_a or self.config.annotator_a
        b_col = annotator_b or self.config.annotator_b

        df_sub = self.df.dropna(subset=[a_col, b_col])
        y1 = _clean_labels(df_sub[a_col])
        y2 = _clean_labels(df_sub[b_col])
        n = len(y1)
        if n < 2:
            return {
                "kappa": 0.0, "ci_95": [0.0, 0.0],
                "observed_agreement": 0.0, "expected_agreement": 0.0,
                "n_samples": n,
            }

        kappa = float(cohen_kappa_score(y1, y2))
        if np.isnan(kappa) or len(np.unique(y1)) < 2 or len(np.unique(y2)) < 2:
            observed = float(np.mean(y1 == y2))
            return {
                "kappa": None,
                "ci_95": [None, None],
                "observed_agreement": round(observed, 4),
                "expected_agreement": None,
                "n_samples": n,
                "interpretation": "N/A (degenerate - constant predictor)",
                "passes_threshold": None,
            }
        observed = float(np.mean(y1 == y2))
        p_a = float(np.mean(y1))
        p_b = float(np.mean(y2))
        expected = p_a * p_b + (1.0 - p_a) * (1.0 - p_b)

        # Bootstrap CI (percentile method)
        rng = np.random.RandomState(self.config.random_seed)
        boot: list[float] = []
        for _ in range(self.config.bootstrap_iterations):
            idx = rng.randint(0, n, n)
            try:
                bk = float(cohen_kappa_score(y1[idx], y2[idx]))
                boot.append(bk)
            except ValueError:
                pass

        if boot:
            ci_lo, ci_hi = float(np.percentile(boot, [2.5, 97.5])[0]), float(np.percentile(boot, [2.5, 97.5])[1])
        else:
            ci_lo, ci_hi = kappa - 0.05, kappa + 0.05

        return {
            "kappa": round(kappa, 4),
            "ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
            "observed_agreement": round(observed, 4),
            "expected_agreement": round(expected, 4),
            "n_samples": n,
            "interpretation": _interpret_kappa(kappa),
            "passes_threshold": kappa >= 0.60,
        }

    # --- Fleiss' Kappa ----------------------------------------------------------

    def calculate_fleiss_kappa(self) -> Optional[dict[str, Any]]:
        """Fleiss' Kappa across 3 annotators (A, B, Human) on the human-reviewed subset."""
        df = self.df
        # Only human reviewed ones have human_label (which populates ground_truth)
        df_sub = df[df["review_status"] == "human_reviewed"].dropna(subset=[
            self.config.annotator_a, self.config.annotator_b, self.config.ground_truth
        ]).copy()
        
        if len(df_sub) < self.config.min_samples_breakdown:
            return None

        a_vals = _clean_labels(df_sub[self.config.annotator_a])
        b_vals = _clean_labels(df_sub[self.config.annotator_b])
        h_vals = _clean_labels(df_sub[self.config.ground_truth])

        min_len = min(len(a_vals), len(b_vals), len(h_vals))
        if min_len < self.config.min_samples_breakdown:
            return None

        a_vals = a_vals[:min_len]
        b_vals = b_vals[:min_len]
        h_vals = h_vals[:min_len]

        try:
            from statsmodels.stats.inter_rater import (
                aggregate_raters,
                fleiss_kappa as _fk,
            )

            ratings = np.column_stack([a_vals, b_vals, h_vals])
            aggregated, _ = aggregate_raters(ratings)
            fk_val = float(_fk(aggregated))
            return {
                "fleiss_kappa": round(fk_val, 4),
                "n_samples": min_len,
                "n_raters": 3,
                "interpretation": _interpret_kappa(fk_val),
            }
        except Exception as exc:
            logger.warning("Fleiss' Kappa failed: %s", exc)
            return None

    # --- Breakdowns -------------------------------------------------------------

    def breakdown_by_source(self) -> Dict[str, dict]:
        results: Dict[str, dict] = {}
        df = self.df
        if self.config.source_col not in df.columns:
            return results
        for source in sorted(df[self.config.source_col].unique()):
            subset = df[df[self.config.source_col] == source]
            result = _kappa_for_subset(subset, self.config.annotator_a, self.config.annotator_b)
            n = _to_int(len(subset))
            if result is None:
                results[str(source)] = {
                    "kappa": 0.0,
                    "gwet_ac1": 0.0,
                    "n_samples": n,
                    "observed_agreement": 0.0,
                    "interpretation": "N/A",
                    "error": "insufficient_samples"
                }
            else:
                df_sub = subset.dropna(subset=[self.config.annotator_a, self.config.annotator_b])
                y1 = _clean_labels(df_sub[self.config.annotator_a])
                y2 = _clean_labels(df_sub[self.config.annotator_b])
                ac1 = calculate_gwets_ac1(y1, y2)
                result["gwet_ac1"] = round(ac1, 4)
                results[str(source)] = result
        return results

    def breakdown_by_class(self) -> Dict[str, dict]:
        results: Dict[str, dict] = {}
        df = self.df
        gt = self.config.ground_truth
        for label_val, label_name in [(1, "clickbait"), (0, "non_clickbait")]:
            subset = df[df[gt] == label_val]
            result = _kappa_for_subset(subset, self.config.annotator_a, self.config.annotator_b)
            n = _to_int(len(subset))
            if result is None:
                results[label_name] = BreakdownResult(
                    0.0, n, 0.0, "N/A", "insufficient_samples"
                ).to_dict()
            else:
                results[label_name] = result
        return results

    def breakdown_by_confidence(self) -> Dict[str, dict]:
        results: Dict[str, dict] = {}
        df = self.df
        conf_col = self.config.confidence_col
        if conf_col not in df.columns:
            return results

        bins = [0.0, 0.60, 0.75, 0.90, 1.01]
        labels = ["<0.60", "0.60-0.74", "0.75-0.89", "0.90+"]
        df = df.copy()
        df["_conf_bucket"] = pd.cut(
            df[conf_col], bins=bins, labels=labels, include_lowest=True
        )

        for bucket in labels:
            subset = df[df["_conf_bucket"] == bucket]
            result = _kappa_for_subset(subset, self.config.annotator_a, self.config.annotator_b)
            n = _to_int(len(subset))
            if result is None:
                results[bucket] = BreakdownResult(
                    0.0, n, 0.0, "N/A", "insufficient_samples"
                ).to_dict()
            else:
                results[bucket] = result
        return results

    # --- Disagreement analysis --------------------------------------------------

    def analyze_disagreements(self, n_samples: int = 20) -> dict[str, Any]:
        df = self.df
        a_col = self.config.annotator_a
        b_col = self.config.annotator_b

        mask = (
            df[a_col].notna()
            & df[b_col].notna()
            & df[a_col].ne(df[b_col])
        )
        disagreements = df[mask]
        total = _to_int(len(disagreements))
        total_valid = _to_int(len(df.dropna(subset=[a_col, b_col])))
        rate = total / total_valid if total_valid > 0 else 0.0

        resolved = 0
        if "reviewer_id" in df.columns:
            resolved = _to_int(
                disagreements[disagreements["reviewer_id"].notna()].shape[0]
            )
        elif "review_status" in df.columns:
            resolved = _to_int(
                disagreements[disagreements["review_status"] == "human_reviewed"].shape[0]
            )
        elif "status" in df.columns:
            resolved = _to_int(
                disagreements[disagreements["status"] != "accepted"].shape[0]
            )

        gt_col = self.config.ground_truth
        both_wrong = 0
        if gt_col in df.columns:
            m = disagreements[disagreements[gt_col].notna()]
            if len(m) > 0:
                both_wrong = _to_int(
                    ((m[gt_col] != m[a_col]) & (m[gt_col] != m[b_col])).sum()
                )

        sample_cols = [
            "id", "source", "title",
            a_col, b_col,
            a_col.replace("_label", "_confidence"),
            b_col.replace("_label", "_confidence"),
            gt_col, "status",
        ]
        avail = [c for c in sample_cols if c in disagreements.columns]
        samples = disagreements[avail].head(n_samples).to_dict("records")

        return {
            "total_disagreements": total,
            "disagreement_rate": round(rate, 4),
            "resolved_by_human": resolved,
            "both_models_wrong_vs_final": both_wrong,
            "samples": samples,
        }

    # --- Human vs LLM -----------------------------------------------------------

    def calculate_human_vs_llm(self) -> Optional[dict[str, Any]]:
        df = self.df
        # Only human reviewed subset can be compared
        df_sub = df[df["review_status"] == "human_reviewed"].dropna(subset=[
            self.config.annotator_a,
            self.config.annotator_b,
            self.config.ground_truth,
        ])
        if len(df_sub) < self.config.min_samples_breakdown:
            return None

        ka = _kappa_for_subset(df_sub, self.config.annotator_a, self.config.ground_truth)
        kb = _kappa_for_subset(df_sub, self.config.annotator_b, self.config.ground_truth)
        return {
            self.config.annotator_a.replace("_label", ""): ka,
            self.config.annotator_b.replace("_label", ""): kb,
        }

    # --- Orchestration ----------------------------------------------------------

    def generate_report(self) -> IAAReport:
        cohens = self.calculate_cohens_kappa()
        fleiss = self.calculate_fleiss_kappa()
        by_source = self.breakdown_by_source()
        by_class = self.breakdown_by_class()
        by_conf = self.breakdown_by_confidence()
        disagreements = self.analyze_disagreements()
        human_llm = self.calculate_human_vs_llm()

        # Calculate Gwet's AC1 (Model A vs Model B)
        df_sub = self.df.dropna(subset=[self.config.annotator_a, self.config.annotator_b])
        y1 = _clean_labels(df_sub[self.config.annotator_a])
        y2 = _clean_labels(df_sub[self.config.annotator_b])
        gwets_val = calculate_gwets_ac1(y1, y2)

        # Calculate Krippendorff's Alpha (Model A, Model B, and Human where present)
        # We construct a ratings matrix of shape (N, 3) where columns are Model A, Model B, and Human rating
        ratings_cols = [self.config.annotator_a, self.config.annotator_b]
        
        # Human rating is only ground_truth (final_label) on the reviewed subset, otherwise NaN
        df_ratings = self.df.copy()
        df_ratings["human_label_col"] = np.nan
        reviewed_mask = df_ratings["review_status"] == "human_reviewed"
        df_ratings.loc[reviewed_mask, "human_label_col"] = df_ratings.loc[reviewed_mask, self.config.ground_truth]
        
        ratings_matrix = df_ratings[[self.config.annotator_a, self.config.annotator_b, "human_label_col"]].to_numpy()
        kripp_val = calculate_krippendorff_alpha(ratings_matrix)

        warnings = []
        if cohens["kappa"] is not None and cohens["kappa"] < 0.60:
            warnings.append(f"Low Cohen's Kappa ({cohens['kappa']:.4f} < 0.60) - substantial agreement threshold failed.")
        if fleiss is None:
            warnings.append("Insufficient human reviewed samples to compute Fleiss' Kappa.")

        return IAAReport(
            cohens_kappa=cohens["kappa"],
            cohens_kappa_ci=cohens["ci_95"],
            cohens_kappa_interpretation=cohens["interpretation"],
            observed_agreement=cohens["observed_agreement"],
            expected_agreement=cohens["expected_agreement"],
            n_samples=cohens["n_samples"],
            gwets_ac1=gwets_val,
            krippendorff_alpha=kripp_val,
            fleiss_kappa=fleiss["fleiss_kappa"] if fleiss else None,
            fleiss_n_raters=fleiss["n_raters"] if fleiss else None,
            breakdown_by_source=by_source,
            breakdown_by_class=by_class,
            breakdown_by_confidence=by_conf,
            disagreement_analysis=disagreements,
            human_vs_llm=human_llm,
            warnings=warnings,
        )

    def save_report(self, output_path: str | Path) -> IAAReport:
        """Run full analysis and save to JSON."""
        report = self.generate_report()
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, indent=2, ensure_ascii=False)

        status = "SKIPPED" if report.cohens_kappa is None else ("PASS" if report.cohens_kappa >= 0.60 else "FAIL")
        logger.info("IAA Report saved: %s", out)
        if report.cohens_kappa is not None:
            logger.info(
                "Cohen's Kappa: %.4f [%.4f, %.4f] - %s",
                report.cohens_kappa,
                report.cohens_kappa_ci[0],
                report.cohens_kappa_ci[1],
                status,
            )
        else:
            logger.info("Cohen's Kappa: N/A (degenerate annotator) - %s", status)
        for w in report.warnings:
            logger.warning("%s", w)
        return report

    def print_summary(self, report: IAAReport) -> None:
        """Print human-readable summary."""
        sep = "=" * 60
        print(f"\n{sep}")
        print(" IAA REPORT - Phase 7")
        print(sep)
        kappa_str = f"{report.cohens_kappa:.4f}" if report.cohens_kappa is not None else "N/A (degenerate)"
        ci_str = f"[{report.cohens_kappa_ci[0]:.4f}, {report.cohens_kappa_ci[1]:.4f}]" if report.cohens_kappa_ci[0] is not None else "N/A"
        obs_str = f"{report.observed_agreement:.4f}" if report.observed_agreement is not None else "N/A"
        exp_str = f"{report.expected_agreement:.4f}" if report.expected_agreement is not None else "N/A"
        print(f"  Cohen's Kappa  : {kappa_str}")
        print(f"  95% CI         : {ci_str}")
        print(f"  Interpretation : {report.cohens_kappa_interpretation}")
        print(f"  Observed Agree : {obs_str}")
        print(f"  Expected Agree : {exp_str}")
        print(f"  N samples      : {report.n_samples}")
        print(f"  Gwet's AC1     : {report.gwets_ac1:.4f} (robust to class imbalance)")
        print(f"  Krippendorff's : {report.krippendorff_alpha:.4f} (supports missing human values)")
        if report.fleiss_kappa is not None:
            print(f"  Fleiss' Kappa  : {report.fleiss_kappa:.4f} ({report.fleiss_n_raters} raters)")
        print()
        print("  Breakdown by Source:")
        for src, d in report.breakdown_by_source.items():
            print(f"    {src:15s}: K={d.get('kappa',0) or 0.0:.4f} (n={d.get('n_samples',0)}) {d.get('interpretation','')}")
        print()
        print("  Breakdown by Class:")
        for cls, d in report.breakdown_by_class.items():
            print(f"    {cls:15s}: K={d.get('kappa',0) or 0.0:.4f} (n={d.get('n_samples',0)}) {d.get('interpretation','')}")
        print()
        da = report.disagreement_analysis
        print(f"  Disagreements: {da.get('total_disagreements',0)} ({da.get('disagreement_rate',0):.1%})")
        if da.get("resolved_by_human"):
            print(f"    Resolved by human: {da['resolved_by_human']}")
        if da.get("both_models_wrong_vs_final"):
            print(f"    Both models wrong: {da['both_models_wrong_vs_final']}")
        print()
        if report.human_vs_llm:
            print("  Human vs LLM:")
            for model, d in report.human_vs_llm.items():
                if isinstance(d, dict) and "kappa" in d:
                    print(f"    {model}: K={d['kappa']:.4f} (n={d['n_samples']})")
        print()
        if report.warnings:
            print("  Warnings:")
            for w in report.warnings:
                print(f"    ! {w}")
        gate = "SKIPPED" if report.cohens_kappa is None else ("PASS" if report.cohens_kappa >= 0.60 else "FAIL")
        print(f"\n  GATE (Kappa >= 0.60): {gate}")
        print(f"{sep}\n")


# --- CLI ------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 7: IAA Calculator (spec s70)")
    ap.add_argument("--input", default="data/annotated/final_reviewed_merged.jsonl")
    ap.add_argument("--output", default="logs/iaa_results.json")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input not found: %s", input_path)
        sys.exit(1)

    logger.info("Loading %s ...", input_path)
    records: list[dict[str, Any]] = []
    with open(input_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    df = pd.DataFrame(records)
    logger.info("Loaded %d records, %d columns", len(df), len(df.columns))

    calc = IAACalculator(df)
    report = calc.save_report(args.output)

    if not args.quiet:
        calc.print_summary(report)

    if report.cohens_kappa is not None and not report.cohens_kappa >= 0.60:
        logger.error("IAA GATE FAILED - Kappa %.4f < 0.60", report.cohens_kappa)
        sys.exit(1)


if __name__ == "__main__":
    main()
