"""EDA Visualizer - Phase 7 (spec s69).

25 publication-ready figures for Vietnamese Clickbait Dataset analysis.
All labels, titles, and legends are in Vietnamese for scientific reporting.
Uses matplotlib + seaborn with Okabe-Ito colorblind-friendly palette.
All figures saved to data/final/figures/ at 300 DPI.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)

# Okabe-Ito colorblind-friendly palette
OKABE_ITO = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#999999"]
CB_CLICKBAIT = "#D55E00"  # reddish
CB_NON_CLICKBAIT = "#009E73"  # greenish
CB_HIGHLIGHT = "#F0E442"  # yellow
CB_ACCENT = "#0072B2"  # blue
CB_NEUTRAL = "#999999"  # gray

sns.set_style("whitegrid")
sns.set_context("paper", font_scale=1.1)
matplotlib.rcParams["figure.dpi"] = 150
matplotlib.rcParams["savefig.dpi"] = 300
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial Unicode MS", "Noto Sans", "Liberation Sans", "sans-serif"]
matplotlib.rcParams["axes.unicode_minus"] = False


class EDAVisualizer:
    def __init__(self, output_dir: str = "data/final/figures"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.figures_generated: list[str] = []

    def _save(self, name: str, fig: plt.Figure) -> str:
        path = self.output_dir / f"{name}.png"
        fig.savefig(path, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        self.figures_generated.append(name)
        logger.info("Saved: %s", path)
        return str(path)

    def generate_all(self, df: pd.DataFrame, iaa_report: dict[str, Any] | None = None) -> list[str]:
        self.figures_generated = []
        
        # Preprocess localized labels for plots
        df_plot = df.copy()
        if "label_name" in df_plot.columns:
            df_plot["label_name"] = df_plot["label_name"].map({
                "non_clickbait": "Không clickbait",
                "clickbait": "Clickbait"
            }).fillna(df_plot["label_name"])
            
        if "status" in df_plot.columns:
            df_plot["status"] = df_plot["status"].map({
                "accepted": "Tự động chấp nhận",
                "review": "Chuyển kiểm duyệt"
            }).fillna(df_plot["status"])

        figs = [
            self.fig_source_distribution,
            self.fig_status_flow,
            self.fig_bootstrap_distribution,
            self.fig_class_distribution,
            self.fig_source_class_crosstab,
            self.fig_title_length_by_label,
            self.fig_word_length_distribution,
            self.fig_linguistic_markers,
            self.fig_confidence_calibration,
            self.fig_confusion_model_vs_final,
        ]
        
        for fn in figs:
            try:
                fn(df_plot, iaa_report)
            except Exception as exc:
                logger.warning("Figure %s failed: %s", fn.__name__, exc)
                
        logger.info("Generated %d figures", len(self.figures_generated))
        return self.figures_generated

    # ---- Figure 4: Class distribution ------------------------------------------

    def fig_class_distribution(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        label_col = "label_name" if "label_name" in df.columns else "final_label"
        counts = df[label_col].value_counts()
        fig, ax = plt.subplots(figsize=(6, 4))
        
        index_mapped = []
        for val in counts.index:
            if val == 0 or val == "non_clickbait" or val == "Không clickbait":
                index_mapped.append("Không clickbait (0)")
            elif val == 1 or val == "clickbait" or val == "Clickbait":
                index_mapped.append("Clickbait (1)")
            else:
                index_mapped.append(str(val))
                
        color_map = {
            "Không clickbait (0)": CB_NON_CLICKBAIT,
            "Clickbait (1)": CB_CLICKBAIT
        }
        bar_colors = [color_map.get(lbl, CB_NEUTRAL) for lbl in index_mapped]
        
        bars = ax.bar(index_mapped, counts.values, color=bar_colors, edgecolor="white", linewidth=0.5)
        for bar, val in zip(bars, counts.values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 20,
                    f"{val}\n({val / counts.sum():.1%})", ha="center", va="bottom", fontsize=11, fontweight="bold")
                    
        ax.set_title("Phân phối nhãn mục tiêu", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Nhãn", fontsize=12)
        ax.set_ylabel("Số lượng", fontsize=12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("fig_04_class_distribution", fig)

    # ---- Figure 1: Source distribution -----------------------------------------

    def fig_source_distribution(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        dedup_path = Path("data/dedup/final_deduped.jsonl")
        if dedup_path.exists():
            try:
                import json
                sources = []
                with open(dedup_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            obj = json.loads(line)
                            if "source" in obj:
                                sources.append(obj["source"])
                counts = pd.Series(sources).value_counts()
            except Exception as e:
                logger.warning("Failed to load deduped data: %s", e)
                counts = df["source"].value_counts()
        else:
            counts = df["source"].value_counts()
            
        fig, ax = plt.subplots(figsize=(8, 4))
        bars = ax.barh(counts.index[::-1], counts.values[::-1], color=CB_ACCENT, edgecolor="white")
        for bar, val in zip(bars, counts.values[::-1]):
            ax.text(val + 20, bar.get_y() + bar.get_height() / 2,
                    f"{val} ({val / counts.sum():.1%})", va="center", fontsize=10)
        ax.set_title("Phân phối mẫu theo nguồn báo", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Số lượng", fontsize=12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("fig_01_source_distribution", fig)

    # ---- Figure 3: Confidence distribution -------------------------------------

    def fig_confidence_distribution(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        if "confidence" not in df.columns:
            return
        fig, ax = plt.subplots(figsize=(7, 4))
        sns.histplot(data=df, x="confidence", bins=30, kde=True,
                     color=CB_ACCENT, ax=ax, alpha=0.7)
        ax.axvline(df["confidence"].mean(), color=CB_CLICKBAIT, linestyle="--", linewidth=2,
                   label=f"Trung bình = {df['confidence'].mean():.3f}")
        ax.set_title("Phân phối điểm số tin cậy", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Độ tin cậy", fontsize=12)
        ax.set_ylabel("Số lượng", fontsize=12)
        ax.legend()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("03_confidence_distribution", fig)

    # ---- Figure 4: Confidence by label -----------------------------------------

    def fig_confidence_by_label(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        label_col = "label_name" if "label_name" in df.columns else "final_label"
        if "confidence" not in df.columns or label_col not in df.columns:
            return
        fig, ax = plt.subplots(figsize=(7, 4))
        sns.violinplot(data=df, x=label_col, y="confidence",
                       palette=[CB_NON_CLICKBAIT, CB_CLICKBAIT], ax=ax)
        ax.set_title("Điểm số tin cậy theo nhãn mục tiêu", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Nhãn", fontsize=12)
        ax.set_ylabel("Độ tin cậy", fontsize=12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("04_confidence_by_label", fig)

    # ---- Figure 5: Quality score distribution ----------------------------------

    def fig_quality_distribution(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        if "quality_score" not in df.columns:
            return
        fig, ax = plt.subplots(figsize=(7, 4))
        sns.histplot(data=df, x="quality_score", bins=range(3, 8),
                     color=CB_HIGHLIGHT, ax=ax, alpha=0.8, edgecolor="white")
        ax.axvline(df["quality_score"].mean(), color=CB_ACCENT, linestyle="--", linewidth=2,
                   label=f"Trung bình = {df['quality_score'].mean():.2f}")
        ax.set_title("Phân phối điểm số chất lượng trích xuất", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Điểm chất lượng", fontsize=12)
        ax.set_ylabel("Số lượng", fontsize=12)
        ax.legend()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("05_quality_distribution", fig)

    # ---- Figure 6: Cohen's Kappa by source (bar) -------------------------------

    def fig_cohens_by_source(self, df: pd.DataFrame, iaa_report: dict | None = None) -> None:
        if iaa_report is None or "breakdown" not in iaa_report or "by_source" not in iaa_report["breakdown"]:
            return
        breakdown = iaa_report["breakdown"]["by_source"]
        sources = list(breakdown.keys())
        kappas = [breakdown[s].get("kappa") for s in sources]
        gwets = [breakdown[s].get("gwet_ac1") for s in sources]
        
        # Handle Nones
        kappas = [k if k is not None else 0.0 for k in kappas]
        gwets = [g if g is not None else 0.0 for g in gwets]

        fig, ax = plt.subplots(figsize=(8, max(4, len(sources) * 0.6)))
        y = np.arange(len(sources))
        height = 0.35

        ax.barh(y - height/2, kappas, height, label="Hệ số Cohen's Kappa", color=CB_ACCENT, edgecolor="white")
        ax.barh(y + height/2, gwets, height, label="Hệ số Gwet's AC1", color=CB_NON_CLICKBAIT, edgecolor="white")

        ax.axvline(0.6, color=CB_CLICKBAIT, linestyle="--", linewidth=1.5, label="Ngưỡng mục tiêu (0.60)")
        ax.set_yticks(y)
        ax.set_yticklabels(sources)
        ax.set_xlim(min(min(kappas), min(gwets), -0.6) - 0.1, 1.05)
        ax.set_title("Độ thỏa thuận liên đánh giá theo nguồn báo (Kappa vs Gwet's AC1)", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Giá trị", fontsize=12)
        ax.legend()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("06_cohens_by_source", fig)

    # ---- Figure 7: Agreement matrix (heatmap) ----------------------------------

    def fig_agreement_matrix(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        model_a_col = "model_a_label" if "model_a_label" in df.columns else None
        model_b_col = "model_b_label" if "model_b_label" in df.columns else None
        gt_col = "final_label" if "final_label" in df.columns else None
        if not all([model_a_col, model_b_col, gt_col]):
            return
        labels = sorted(df[gt_col].dropna().unique())
        data = []
        for gt in labels:
            row = []
            for pred in labels:
                cnt = len(df[(df[gt_col] == gt) & (df[model_a_col] == pred)])
                row.append(cnt)
            data.append(row)
        fig, ax = plt.subplots(figsize=(6, 5))
        sns.heatmap(data, annot=True, fmt="d", cmap="Blues",
                    xticklabels=[f"Dự đoán {int(l)}" for l in labels],
                    yticklabels=[f"Nhãn vàng {int(l)}" for l in labels], ax=ax)
        ax.set_title("Ma trận đồng thuận Model A vs Nhãn vàng", fontsize=14, fontweight="bold", pad=12)
        self._save("07_agreement_matrix", fig)

    # ---- Figure 8: Disagreement rate by source ---------------------------------

    def fig_disagreement_by_source(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        model_a_col = "model_a_label" if "model_a_label" in df.columns else None
        model_b_col = "model_b_label" if "model_b_label" in df.columns else None
        if not all([model_a_col, model_b_col, "source" in df.columns]):
            return
        df_valid = df.dropna(subset=[model_a_col, model_b_col]).copy()
        if len(df_valid) == 0:
            return
        df_valid["disagree"] = df_valid[model_a_col] != df_valid[model_b_col]
        rates = df_valid.groupby("source")["disagree"].mean() * 100
        fig, ax = plt.subplots(figsize=(8, max(4, len(rates) * 0.5)))
        ax.barh(rates.index[::-1], rates.values[::-1], color=CB_CLICKBAIT, edgecolor="white", alpha=0.8)
        ax.set_title("Tỷ lệ bất đồng thuận theo nguồn báo", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Tỷ lệ bất đồng thuận (%)", fontsize=12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("08_disagreement_by_source", fig)

    # ---- Figure 9: Confidence calibration curve --------------------------------

    def fig_confidence_calibration(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        if "confidence" not in df.columns or "final_label" not in df.columns:
            return
        df_valid = df.dropna(subset=["confidence", "final_label"])
        if len(df_valid) == 0:
            return
        bins = np.linspace(0, 1, 11)
        bin_centers = (bins[:-1] + bins[1:]) / 2
        accuracies = []
        counts = []
        for i in range(len(bins) - 1):
            mask = (df_valid["confidence"] >= bins[i]) & (df_valid["confidence"] < bins[i + 1])
            subset = df_valid[mask]
            if len(subset) > 0:
                accuracies.append((subset["final_label"] == (subset["confidence"] > 0.5)).mean())
                counts.append(len(subset))
            else:
                accuracies.append(np.nan)
                counts.append(0)
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.plot(bin_centers, accuracies, "o-", color=CB_ACCENT, linewidth=2, markersize=8, label="Độ chính xác thực tế")
        ax.plot([0, 1], [0, 1], "--", color=CB_NEUTRAL, linewidth=1.5, label="Đường hiệu chuẩn lý tưởng")
        ax.set_title("Đường cong hiệu chuẩn độ tin cậy", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Độ tin cậy dự báo", fontsize=12)
        ax.set_ylabel("Độ chính xác quan sát thực tế", fontsize=12)
        ax.legend()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("fig_09_confidence_calibration", fig)

    # ---- Figure 10: Rubric score distribution (grouped bar) --------------------

    def fig_rubric_distribution(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        prefix_a = "model_a"
        prefix_b = "model_b"
        criteria_names = ["C1_info_hiding", "C2_emotional", "C3_misleading", "C4_urgency"]
        model_data: dict[str, pd.Series] = {}
        for prefix in [prefix_a, prefix_b]:
            col = f"{prefix}_rubric_total"
            if col in df.columns:
                model_data[prefix] = df[col].dropna()
        if not model_data:
            return
        fig, ax = plt.subplots(figsize=(8, 4))
        x = np.arange(len(criteria_names))
        width = 0.35
        for i, (model, data) in enumerate(model_data.items()):
            means = []
            for _, cname in [(0, criteria_names[0]), (1, criteria_names[1]),
                             (2, criteria_names[2]), (3, criteria_names[3])]:
                col = f"{model}_{cname}"
                if col in df.columns:
                    vals = df[col].dropna()
                    means.append(vals.mean() if len(vals) > 0 else 0)
                else:
                    means.append(0)
            offset = width * (i - 0.5)
            label = "Qwen 2.5 3B (Mô hình A)" if model == "model_a" else "Gemma 2 2B (Mô hình B)"
            color = CB_ACCENT if model == "model_a" else CB_CLICKBAIT
            bars = ax.bar(x + offset, means, width, label=label, color=color, alpha=0.8, edgecolor="white")
        ax.set_title("Điểm rubric trung bình theo từng tiêu chí BARS", fontsize=14, fontweight="bold", pad=12)
        ax.set_xticks(x)
        ax.set_xticklabels(["C1: Ẩn giấu TT", "C2: Phóng đại CX", "C3: Gây hiểu lầm", "C4: Khẩn cấp giả"], fontsize=10)
        ax.set_ylabel("Điểm trung bình (0-2)", fontsize=12)
        ax.legend()
        ax.set_ylim(0, 2.2)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("10_rubric_distribution", fig)

    # ---- Figure 11: Severity distribution --------------------------------------

    def fig_severity_distribution(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        if "disagreement_severity" not in df.columns:
            return
        counts = df["disagreement_severity"].value_counts().sort_index()
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(counts.index.astype(str), counts.values, color=CB_HIGHLIGHT, edgecolor="white")
        ax.set_title("Phân phối mức độ nghiêm trọng bất đồng thuận", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Mức độ nghiêm trọng", fontsize=12)
        ax.set_ylabel("Số lượng", fontsize=12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("11_severity_distribution", fig)

    # ---- Figure 12: Model agreement vs confidence (scatter) --------------------

    def fig_model_agreement_vs_confidence(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        model_a_col = "model_a_label" if "model_a_label" in df.columns else None
        model_b_col = "model_b_label" if "model_b_label" in df.columns else None
        conf_col = "confidence" if "confidence" in df.columns else None
        if not all([model_a_col, model_b_col, conf_col]):
            return
        df_valid = df.dropna(subset=[model_a_col, model_b_col, conf_col]).copy()
        if len(df_valid) == 0:
            return
        df_valid["agree"] = df_valid[model_a_col] == df_valid[model_b_col]
        agree_data = df_valid[df_valid["agree"]]
        disagree_data = df_valid[~df_valid["agree"]]
        fig, ax = plt.subplots(figsize=(7, 5))
        if len(agree_data) > 0:
            ax.scatter(agree_data[conf_col], agree_data["agree"].astype(int),
                       alpha=0.5, s=30, color=CB_NON_CLICKBAIT, label="Đồng thuận")
        if len(disagree_data) > 0:
            ax.scatter(disagree_data[conf_col], disagree_data["agree"].astype(int),
                       alpha=0.5, s=30, color=CB_CLICKBAIT, label="Bất đồng thuận")
        ax.set_title("Độ đồng thuận mô hình theo điểm tin cậy", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Điểm tin cậy", fontsize=12)
        ax.set_ylabel("Đồng thuận (0=Không, 1=Có)", fontsize=12)
        ax.legend()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("12_model_agreement_vs_confidence", fig)

    # ---- Figure 13: Label distribution over time (line) ------------------------

    def fig_temporal_trend(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        if "crawl_date" not in df.columns or "label_name" not in df.columns:
            return
        df_valid = df.dropna(subset=["crawl_date", "label_name"])
        if len(df_valid) == 0:
            return
        daily = df_valid.groupby(["crawl_date", "label_name"]).size().unstack(fill_value=0)
        if "Clickbait" not in daily.columns:
            daily["Clickbait"] = 0
        daily["clickbait_pct"] = daily["Clickbait"] / daily.sum(axis=1) * 100
        fig, ax1 = plt.subplots(figsize=(10, 4))
        ax1.bar(daily.index, daily.sum(axis=1), color=CB_ACCENT, alpha=0.3, label="Tổng cộng")
        ax1.set_xlabel("Ngày", fontsize=12)
        ax1.set_ylabel("Tổng số bài báo", fontsize=12, color=CB_ACCENT)
        ax1.tick_params(axis="y", labelcolor=CB_ACCENT)
        ax2 = ax1.twinx()
        ax2.plot(daily.index, daily["clickbait_pct"], color=CB_CLICKBAIT,
                 linewidth=2, marker="o", markersize=4, label="Tỷ lệ clickbait (%)")
        ax2.set_ylabel("Tỷ lệ clickbait (%)", fontsize=12, color=CB_CLICKBAIT)
        ax2.tick_params(axis="y", labelcolor=CB_CLICKBAIT)
        ax2.set_ylim(0, 100)
        ax1.set_title("Tỷ lệ clickbait theo thời gian", fontsize=14, fontweight="bold", pad=12)
        ax1.spines["top"].set_visible(False)
        self._save("13_temporal_trend", fig)

    # ---- Figure 14: Title length by label (violin) -----------------------------

    def fig_title_length_by_label(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        label_col = "label_name" if "label_name" in df.columns else "final_label"
        if "title" not in df.columns or label_col not in df.columns:
            return
        df_valid = df.dropna(subset=["title", label_col]).copy()
        df_valid["title_length"] = df_valid["title"].str.len()
        if len(df_valid) == 0:
            return
            
        df_valid[label_col] = df_valid[label_col].map({
            0: "Không clickbait", 1: "Clickbait",
            "non_clickbait": "Không clickbait", "clickbait": "Clickbait",
            "Không clickbait": "Không clickbait", "Clickbait": "Clickbait"
        }).fillna(df_valid[label_col])
        
        fig, ax = plt.subplots(figsize=(7, 4))
        palette = {
            "Không clickbait": CB_NON_CLICKBAIT,
            "Clickbait": CB_CLICKBAIT
        }
        sns.violinplot(data=df_valid, x=label_col, y="title_length",
                       hue=label_col, palette=palette, legend=False, ax=ax)
        ax.set_title("Phân phối độ dài tiêu đề theo nhãn", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Nhãn", fontsize=12)
        ax.set_ylabel("Độ dài tiêu đề (ký tự)", fontsize=12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("fig_06_title_length_by_label", fig)

    # ---- Figure 15: Confusion-style model vs final label -----------------------

    def fig_confusion_model_vs_final(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        model_a_col = "model_a_label" if "model_a_label" in df.columns else None
        gt_col = "final_label" if "final_label" in df.columns else None
        model_b_col = "model_b_label" if "model_b_label" in df.columns else None
        if not all([model_a_col, model_b_col, gt_col]):
            return
        from sklearn.metrics import confusion_matrix
        df_cm = df.dropna(subset=[gt_col, model_a_col, model_b_col]).copy()
        df_cm[model_a_col] = df_cm[model_a_col].astype(int)
        df_cm[model_b_col] = df_cm[model_b_col].astype(int)
        df_cm[gt_col] = df_cm[gt_col].astype(int)
        labels = sorted(df_cm[gt_col].unique())
        cm_a = confusion_matrix(df_cm[gt_col], df_cm[model_a_col], labels=labels)
        cm_b = confusion_matrix(df_cm[gt_col], df_cm[model_b_col], labels=labels)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        sns.heatmap(cm_a, annot=True, fmt="d", cmap="Blues", ax=ax1,
                    xticklabels=["Không CB (0)", "Clickbait (1)"], yticklabels=["Không CB (0)", "Clickbait (1)"])
        ax1.set_title("Model A (Qwen) vs Nhãn vàng", fontsize=12, fontweight="bold")
        ax1.set_xlabel("Dự đoán", fontsize=10)
        ax1.set_ylabel("Thực tế", fontsize=10)
        sns.heatmap(cm_b, annot=True, fmt="d", cmap="Oranges", ax=ax2,
                    xticklabels=["Không CB (0)", "Clickbait (1)"], yticklabels=["Không CB (0)", "Clickbait (1)"])
        ax2.set_title("Model B (Gemma) vs Nhãn vàng", fontsize=12, fontweight="bold")
        ax2.set_xlabel("Dự đoán", fontsize=10)
        ax2.set_ylabel("Thực tế", fontsize=10)
        fig.suptitle("So sánh dự đoán của mô hình và nhãn vàng final", fontsize=14, fontweight="bold", y=1.02)
        self._save("fig_10_confusion_model_vs_final", fig)

    # ---- Figure 16: Human review status distribution (pie) --------------------

    def fig_review_status(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        if "status" not in df.columns:
            return
        df_local = df.copy()
        df_local["status"] = df_local["status"].map({
            "accepted": "Tự động chấp nhận",
            "review": "Chuyển kiểm duyệt",
            "Tự động chấp nhận": "Tự động chấp nhận",
            "Chuyển kiểm duyệt": "Chuyển kiểm duyệt"
        }).fillna(df_local["status"])
        counts = df_local["status"].value_counts()
        fig, ax = plt.subplots(figsize=(6, 6))
        colors = [CB_ACCENT, CB_CLICKBAIT, CB_NEUTRAL][:len(counts)]
        ax.pie(counts.values, labels=counts.index, autopct="%1.1f%%",
               colors=colors, startangle=90, textprops={"fontsize": 11})
        ax.set_title("Phân phối trạng thái gán nhãn", fontsize=14, fontweight="bold", pad=12)
        self._save("16_review_status", fig)

    # ---- Figure 17: IAA breakdown by class -------------------------------------

    def fig_iaa_by_class(self, df: pd.DataFrame, iaa_report: dict | None = None) -> None:
        if iaa_report is None or "breakdown" not in iaa_report or "by_class" not in iaa_report["breakdown"]:
            return
        breakdown = iaa_report["breakdown"]["by_class"]
        classes = list(breakdown.keys())
        kappas = [breakdown[c]["kappa"] for c in classes]
        
        class_mapping = {"clickbait": "Clickbait", "non_clickbait": "Không clickbait"}
        classes_vn = [class_mapping.get(c, c) for c in classes]

        fig, ax = plt.subplots(figsize=(6, 4))
        colors = [CB_CLICKBAIT if (k is not None and k < 0.6) else CB_ACCENT if (k is not None and k < 0.8) else CB_NEUTRAL if k is None else CB_NON_CLICKBAIT for k in kappas]
        ax.bar(classes_vn, kappas, color=colors, edgecolor="white")
        ax.axhline(0.6, color=CB_CLICKBAIT, linestyle="--", linewidth=1.5, label="Ngưỡng mục tiêu (0.60)")
        ax.set_ylim(min(0, min([k for k in kappas if k is not None] + [0])) - 0.1, 1.0)
        ax.set_title("Hệ số Cohen's Kappa theo từng nhãn", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Nhãn", fontsize=12)
        ax.set_ylabel("Hệ số Kappa", fontsize=12)
        ax.legend()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("17_iaa_by_class", fig)

    # ---- Figure 18: Confidence bucket agreement ---------------------------------

    def fig_confidence_bucket_agreement(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        model_a_col = "model_a_label" if "model_a_label" in df.columns else None
        model_b_col = "model_b_label" if "model_b_label" in df.columns else None
        conf_col = "confidence" if "confidence" in df.columns else None
        if not all([model_a_col, model_b_col, conf_col]):
            return
        df_valid = df.dropna(subset=[model_a_col, model_b_col, conf_col]).copy()
        if len(df_valid) == 0:
            return
        df_valid["agree"] = df_valid[model_a_col] == df_valid[model_b_col]
        df_valid["conf_bucket"] = pd.cut(df_valid[conf_col],
                                          bins=[0.0, 0.60, 0.75, 0.90, 1.01],
                                          labels=["<0.60", "0.60-0.74", "0.75-0.89", "0.90+"], include_lowest=True)
        agree_by_bucket = df_valid.groupby("conf_bucket", observed=True)["agree"].mean() * 100
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(agree_by_bucket.index.astype(str), agree_by_bucket.values,
               color=CB_ACCENT, edgecolor="white")
        ax.set_title("Tỷ lệ đồng thuận theo dải điểm tin cậy", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Dải điểm tin cậy", fontsize=12)
        ax.set_ylabel("Tỷ lệ đồng thuận (%)", fontsize=12)
        ax.set_ylim(0, 110)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("18_confidence_bucket_agreement", fig)

    # ---- Figure 19: Word length distribution by label --------------------------

    def fig_word_length_distribution(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        label_col = "label_name" if "label_name" in df.columns else "final_label"
        if "title" not in df.columns or label_col not in df.columns:
            return
        df_valid = df.dropna(subset=["title", label_col]).copy()
        df_valid["word_count"] = df_valid["title"].str.split().str.len()
        if len(df_valid) == 0:
            return
            
        non_cb_mask = (df_valid[label_col] == "Không clickbait") | (df_valid[label_col] == 0) | (df_valid[label_col] == "non_clickbait")
        cb_mask = (df_valid[label_col] == "Clickbait") | (df_valid[label_col] == 1) | (df_valid[label_col] == "clickbait")
        
        non_cb = df_valid[non_cb_mask]["word_count"]
        cb = df_valid[cb_mask]["word_count"]
        
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(non_cb, bins=range(0, int(non_cb.max()) + 5 if len(non_cb) > 0 else 20), alpha=0.6,
                label="Không clickbait", color=CB_NON_CLICKBAIT, edgecolor="white")
        ax.hist(cb, bins=range(0, int(cb.max()) + 5 if len(cb) > 0 else 20), alpha=0.6,
                label="Clickbait", color=CB_CLICKBAIT, edgecolor="white")
        ax.set_title("Phân phối số từ tiêu đề theo nhãn", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Số lượng từ", fontsize=12)
        ax.set_ylabel("Tần suất", fontsize=12)
        ax.legend()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("fig_07_word_length_distribution", fig)

    # ---- Figure 20: Source x Class cross-tab (heatmap) -------------------------

    def fig_source_class_crosstab(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        label_col = "label_name" if "label_name" in df.columns else "final_label"
        if "source" not in df.columns or label_col not in df.columns:
            return
            
        ct_df = df.copy()
        ct_df[label_col] = ct_df[label_col].map({
            0: "Không clickbait", 1: "Clickbait",
            "non_clickbait": "Không clickbait", "clickbait": "Clickbait",
            "Không clickbait": "Không clickbait", "Clickbait": "Clickbait"
        }).fillna(ct_df[label_col])
        
        ct = pd.crosstab(ct_df["source"], ct_df[label_col], normalize="index") * 100
        fig, ax = plt.subplots(figsize=(8, max(4, len(ct) * 0.6)))
        sns.heatmap(ct, annot=True, fmt=".1f", cmap="RdYlGn_r",
                    vmin=0, vmax=100, ax=ax, cbar_kws={"label": "%"})
        ax.set_title("Tỷ lệ clickbait theo nguồn báo (%)", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Nhãn", fontsize=12)
        ax.set_ylabel("Nguồn báo", fontsize=12)
        self._save("fig_05_source_class_crosstab", fig)

    # ---- Figure 21: Bootstrap Kappa distribution --------------------------------

    def fig_bootstrap_distribution(self, df: pd.DataFrame, iaa_report: dict | None = None) -> None:
        if iaa_report is None or "cohens_kappa_ci" not in iaa_report:
            return
        kappa = iaa_report.get("cohens_kappa")
        if kappa is None:
            return
        ci = iaa_report.get("cohens_kappa_ci", [0, 0])
        fig, ax = plt.subplots(figsize=(7, 4))
        x = np.linspace(max(-1, kappa - 0.3), min(1, kappa + 0.3), 200)
        y = np.exp(-((x - kappa) ** 2) / (2 * ((ci[1] - ci[0]) / 3.92) ** 2))
        ax.fill_between(x, y, alpha=0.3, color=CB_ACCENT)
        ax.axvline(kappa, color=CB_ACCENT, linewidth=2, label=f"Hệ số Kappa = {kappa:.3f}")
        ax.axvline(ci[0], color=CB_CLICKBAIT, linestyle="--", linewidth=1.5, label=f"KTC 95%: [{ci[0]:.3f}, {ci[1]:.3f}]")
        ax.axvline(ci[1], color=CB_CLICKBAIT, linestyle="--", linewidth=1.5)
        ax.axvline(0.6, color=CB_NEUTRAL, linestyle=":", linewidth=1.5, label="Ngưỡng mục tiêu (0.60)")
        ax.set_title("Phân phối Bootstrap hệ số Cohen's Kappa", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Hệ số Cohen's Kappa", fontsize=12)
        ax.set_ylabel("Mật độ (ước lượng)", fontsize=12)
        ax.legend()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("fig_03_bootstrap_distribution", fig)

    # ---- Figure 22: Model confidence comparison (scatter) ----------------------

    def fig_model_confidence_comparison(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        a_col = "model_a_rubric_total" if "model_a_rubric_total" in df.columns else "model_a_confidence"
        b_col = "model_b_rubric_total" if "model_b_rubric_total" in df.columns else "model_b_confidence"
        gt_col = "final_label" if "final_label" in df.columns else None
        if not all([a_col in df.columns, b_col in df.columns, gt_col]):
            return
        df_valid = df.dropna(subset=[a_col, b_col, gt_col]).copy()
        if len(df_valid) == 0:
            return
        colors_map = {0: CB_NON_CLICKBAIT, 1: CB_CLICKBAIT}
        fig, ax = plt.subplots(figsize=(6, 6))
        for label_val, color in colors_map.items():
            subset = df_valid[df_valid[gt_col] == label_val]
            label_name = "Không clickbait" if label_val == 0 else "Clickbait"
            ax.scatter(subset[a_col], subset[b_col], alpha=0.5, s=30,
                       color=color, label=f"Nhãn vàng={label_name}")
        ax.plot([0, 1], [0, 1], "--", color=CB_NEUTRAL, linewidth=1)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_title("So sánh độ tự tin giữa hai mô hình", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Độ tự tin Qwen 2.5 3B", fontsize=12)
        ax.set_ylabel("Độ tự tin Gemma 2 2B", fontsize=12)
        ax.legend()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("22_model_confidence_comparison", fig)

    # ---- Figure 23: Quality score vs Agreement ---------------------------------

    def fig_quality_vs_agreement(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        model_a_col = "model_a_label" if "model_a_label" in df.columns else None
        model_b_col = "model_b_label" if "model_b_label" in df.columns else None
        if not all([model_a_col, model_b_col, "quality_score" in df.columns]):
            return
        df_valid = df.dropna(subset=[model_a_col, model_b_col, "quality_score"]).copy()
        if len(df_valid) == 0:
            return
        df_valid["agree"] = df_valid[model_a_col] == df_valid[model_b_col]
        agree_by_q = df_valid.groupby("quality_score")["agree"].agg(["mean", "count"])
        fig, ax1 = plt.subplots(figsize=(7, 4))
        ax1.bar(agree_by_q.index, agree_by_q["count"], color=CB_NEUTRAL, alpha=0.5, label="Số lượng")
        ax2 = ax1.twinx()
        ax2.plot(agree_by_q.index, agree_by_q["mean"] * 100,
                 color=CB_ACCENT, linewidth=2, marker="o", markersize=6, label="Tỷ lệ đồng thuận (%)")
        ax1.set_title("Độ đồng thuận mô hình theo chất lượng trích xuất", fontsize=14, fontweight="bold", pad=12)
        ax1.set_xlabel("Điểm chất lượng trích xuất", fontsize=12)
        ax1.set_ylabel("Số lượng", fontsize=12, color=CB_NEUTRAL)
        ax2.set_ylabel("Tỷ lệ đồng thuận (%)", fontsize=12, color=CB_ACCENT)
        ax1.spines["top"].set_visible(False)
        self._save("23_quality_vs_agreement", fig)

    # ---- Figure 24: Annotation status flow (stacked bar) -----------------------

    def fig_status_flow(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        if "status" not in df.columns or "source" not in df.columns:
            return
        
        df_local = df.copy()
        df_local["status"] = df_local["status"].map({
            "accepted": "Tự động chấp nhận",
            "review": "Chuyển kiểm duyệt",
            "Tự động chấp nhận": "Tự động chấp nhận",
            "Chuyển kiểm duyệt": "Chuyển kiểm duyệt"
        }).fillna(df_local["status"])

        ct = pd.crosstab(df_local["source"], df_local["status"])
        
        color_map = {
            "Tự động chấp nhận": CB_NON_CLICKBAIT,
            "Chuyển kiểm duyệt": CB_CLICKBAIT
        }
        colors = [color_map.get(col, CB_NEUTRAL) for col in ct.columns]
        
        fig, ax = plt.subplots(figsize=(8, max(4, len(ct) * 0.6)))
        ct.plot(kind="barh", stacked=True, ax=ax, color=colors)
        ax.set_title("Trạng thái gán nhãn theo nguồn báo", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Số lượng", fontsize=12)
        ax.legend(title="Trạng thái", fontsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self._save("fig_02_status_flow", fig)

    # ---- Figure 25: Key metrics dashboard (table) ------------------------------

    def fig_key_metrics_dashboard(self, df: pd.DataFrame, iaa_report: dict | None = None) -> None:
        rows = []
        rows.append(("Tổng số bản ghi", str(len(df))))
        label_col = "label_name" if "label_name" in df.columns else "final_label"
        if label_col in df.columns:
            cb_pct = ((df[label_col] == "Clickbait") | (df[label_col] == 1) | (df[label_col] == "clickbait")).mean() * 100
            rows.append(("Tỷ lệ Clickbait", f"{cb_pct:.1f}%"))
        if "quality_score" in df.columns:
            rows.append(("Chất lượng TB", f"{df['quality_score'].mean():.2f}"))
        if iaa_report:
            k_val = iaa_report.get("cohens_kappa")
            rows.append(("Hệ số Cohen's Kappa", f"{k_val:.4f}" if k_val is not None else "N/A (degenerate)"))
            ci = iaa_report.get("cohens_kappa_ci", [0, 0])
            rows.append(("KTC 95%", f"[{ci[0]:.4f}, {ci[1]:.4f}]" if ci and ci[0] is not None else "N/A"))
            interp = iaa_report.get("cohens_kappa_interpretation", "N/A")
            
            # Map interpretation to Vietnamese
            interp_vn = {
                "Slight": "Mờ nhạt (Slight)",
                "Poor": "Kém (Poor)",
                "Moderate": "Vừa phải (Moderate)",
                "Substantial": "Đáng kể (Substantial)",
                "Almost Perfect": "Gần như hoàn hảo"
            }.get(interp, interp)
            rows.append(("Diễn giải", interp_vn))
            
            fleiss = iaa_report.get("fleiss_kappa")
            if fleiss is not None:
                rows.append(("Hệ số Fleiss' Kappa", f"{fleiss:.4f}"))
        if "confidence" in df.columns:
            rows.append(("Độ tự tin TB", f"{df['confidence'].mean():.3f}"))
            
        ncols = 2
        nrows = (len(rows) + 1) // 2
        fig, ax = plt.subplots(figsize=(8, max(3, nrows * 0.6)))
        ax.axis("off")
        table_data = []
        for i in range(nrows):
            row = []
            for j in range(ncols):
                idx = i + j * nrows
                if idx < len(rows):
                    row.append(rows[idx])
                else:
                    row.append(["", ""])
            table_data.append(row)
        cell_text = [[f"{r[0]}: {r[1]}" for r in row] for row in table_data]
        table = ax.table(cellText=cell_text, cellLoc="left", loc="center",
                         colWidths=[0.45, 0.45])
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        for key, cell in table.get_celld().items():
            cell.set_edgecolor(CB_NEUTRAL)
            cell.set_linewidth(0.5)
            if key[0] == 0:
                cell.set_facecolor(CB_ACCENT)
                cell.set_text_props(color="white", fontweight="bold")
            else:
                cell.set_facecolor("#f8f9fa")
        ax.set_title("Bảng chỉ số tổng quan chính", fontsize=14, fontweight="bold", pad=12)
        self._save("25_key_metrics_dashboard", fig)

    # ---- Figure 20: Linguistic Markers (exclamation, question marks, ellipses) -
    
    def fig_linguistic_markers(self, df: pd.DataFrame, _report: dict | None = None) -> None:
        gt_col = "final_label" if "final_label" in df.columns else None
        if not gt_col or "title_has_qmark" not in df.columns:
            return
        
        metrics = ["title_has_qmark", "title_has_excl", "title_has_ellipsis"]
        labels = ["Dấu hỏi (?)", "Dấu chấm than (!)", "Dấu chấm lửng (...)"]
        
        melted = []
        for metric, label_name in zip(metrics, labels):
            for label in [0, 1]:
                sub = df[df[gt_col] == label]
                pct = sub[metric].mean() * 100
                melted.append({
                    "Đặc trưng": label_name,
                    "Nhãn": "Clickbait" if label == 1 else "Không clickbait",
                    "Tỷ lệ xuất hiện (%)": pct
                })
        
        plot_df = pd.DataFrame(melted)
        
        fig, ax1 = plt.subplots(figsize=(8, 4.5))
        palette = {
            "Không clickbait": CB_NON_CLICKBAIT,
            "Clickbait": CB_CLICKBAIT
        }
        sns.barplot(
            data=plot_df,
            x="Đặc trưng",
            y="Tỷ lệ xuất hiện (%)",
            hue="Nhãn",
            palette=palette,
            ax=ax1,
            edgecolor="white"
        )
        
        for container in ax1.containers:
            ax1.bar_label(container, fmt='%.1f%%', label_type='edge', padding=3, fontsize=9)
            
        ax1.set_title("Các dấu hiệu ngôn ngữ học: Clickbait vs Không clickbait", fontsize=13, fontweight="bold", pad=12)
        ax1.set_xlabel("Đặc trưng ngôn ngữ học", fontsize=11)
        ax1.set_ylabel("Tỷ lệ xuất hiện (%)", fontsize=11)
        ax1.set_ylim(0, max(plot_df["Tỷ lệ xuất hiện (%)"]) + 8)
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)
        ax1.legend(title="Nhãn", loc="upper right")
        
        self._save("fig_08_linguistic_markers", fig)
