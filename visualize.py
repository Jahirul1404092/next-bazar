# -*- coding: utf-8 -*-
"""
Visualization module for Next Bazar price analysis and forecasts.

Generates:
1. Price trend plots per commodity
2. Forecast comparison plots
3. Model performance dashboards
4. Correlation heatmaps between commodities

Author: Jahirul (2026)
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
import seaborn as sns

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUTS_DIR = PROJECT_DIR / "outputs"
PLOTS_DIR = OUTPUTS_DIR / "plots"

# Style
plt.style.use("seaborn-v0_8-whitegrid")
sns.set_palette("husl")
plt.rcParams["figure.figsize"] = (14, 6)
plt.rcParams["figure.dpi"] = 150


def plot_commodity_history(clean_csv: Path, top_n: int = 10):
    """Plot price history for top N commodities by data availability."""
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(clean_csv, parse_dates=["date"])

    # Get top commodities by number of data points
    top_commodities = (
        df.groupby("name")["date"].count()
        .nlargest(top_n)
        .index.tolist()
    )

    fig, axes = plt.subplots(
        (top_n + 1) // 2, 2, figsize=(18, 4 * ((top_n + 1) // 2)),
        sharex=False
    )
    axes = axes.flatten()

    for idx, commodity in enumerate(top_commodities):
        ax = axes[idx]
        subset = df[df["name"] == commodity].sort_values("date")

        ax.plot(subset["date"], subset["price_max"],
                label="Max Price", linewidth=1.2, alpha=0.8)
        ax.plot(subset["date"], subset["price_min"],
                label="Min Price", linewidth=1.0, alpha=0.6, linestyle="--")
        if "price_avg" in subset.columns:
            ax.plot(subset["date"], subset["price_avg"],
                    label="Avg Price", linewidth=1.0, alpha=0.7, linestyle=":")

        ax.set_title(commodity, fontsize=10)
        ax.legend(fontsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.tick_params(axis="x", rotation=45, labelsize=8)
        ax.set_ylabel("Price (BDT)", fontsize=8)

    # Hide unused subplots
    for idx in range(len(top_commodities), len(axes)):
        axes[idx].set_visible(False)

    plt.suptitle("Next Bazar — Price History (Top Commodities)", fontsize=14, y=1.01)
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "price_history.png", bbox_inches="tight")
    plt.close()
    print(f"Saved: {PLOTS_DIR / 'price_history.png'}")


def plot_forecasts(forecasts_csv: Path, clean_csv: Path, n_commodities: int = 6):
    """Plot actual + forecasted prices."""
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    forecasts = pd.read_csv(forecasts_csv, parse_dates=["date"])
    clean = pd.read_csv(clean_csv, parse_dates=["date"])

    commodities = forecasts["commodity"].unique()[:n_commodities]

    fig, axes = plt.subplots(
        (len(commodities) + 1) // 2, 2,
        figsize=(18, 4 * ((len(commodities) + 1) // 2))
    )
    axes = axes.flatten()

    for idx, commodity in enumerate(commodities):
        ax = axes[idx]

        # Historical (last 180 days)
        hist = clean[clean["name"].str.contains(commodity[:10], na=False)]
        if len(hist) == 0:
            continue
        hist = hist.sort_values("date").tail(180)
        price_col = "price_avg" if "price_avg" in hist.columns else "price_max"
        ax.plot(hist["date"], hist[price_col],
                label="Actual", color="steelblue", linewidth=1.5)

        # Forecast by model
        fc = forecasts[forecasts["commodity"] == commodity]
        for model_name, group in fc.groupby("model"):
            ax.plot(group["date"], group["predicted_price"],
                    label=f"Forecast ({model_name})", linewidth=1.2, linestyle="--")

        ax.axvline(x=hist["date"].max(), color="red", linestyle=":",
                   alpha=0.5, label="Forecast Start")

        ax.set_title(commodity, fontsize=10)
        ax.legend(fontsize=7, loc="upper left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.tick_params(axis="x", rotation=45, labelsize=8)
        ax.set_ylabel("Price (BDT)", fontsize=8)

    for idx in range(len(commodities), len(axes)):
        axes[idx].set_visible(False)

    plt.suptitle("Price Forecasts — Next 30 Days", fontsize=14, y=1.01)
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "forecasts.png", bbox_inches="tight")
    plt.close()
    print(f"Saved: {PLOTS_DIR / 'forecasts.png'}")


def plot_model_comparison(results_csv: Path):
    """Compare model performance across commodities."""
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    results = pd.read_csv(results_csv)

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    metrics = ["cv_mae", "cv_rmse", "cv_mape", "cv_dir_acc"]
    titles = ["Cross-Val MAE", "Cross-Val RMSE", "Cross-Val MAPE (%)", "Directional Accuracy (%)"]

    for ax, metric, title in zip(axes.flatten(), metrics, titles):
        if metric in results.columns:
            pivot = results.pivot_table(
                index="commodity", columns="model", values=metric, aggfunc="mean"
            )
            pivot.plot(kind="barh", ax=ax, width=0.8)
            ax.set_title(title, fontsize=11)
            ax.set_xlabel(metric.upper(), fontsize=9)
            ax.legend(fontsize=8)
            ax.tick_params(axis="y", labelsize=7)

    plt.suptitle("Model Comparison Across Commodities", fontsize=14)
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "model_comparison.png", bbox_inches="tight")
    plt.close()
    print(f"Saved: {PLOTS_DIR / 'model_comparison.png'}")


def plot_correlation_matrix(clean_csv: Path, top_n: int = 15):
    """Plot price correlation between top commodities."""
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(clean_csv, parse_dates=["date"])

    top = df.groupby("name")["date"].count().nlargest(top_n).index
    subset = df[df["name"].isin(top)]

    # Pivot to get commodity prices as columns
    pivot = subset.pivot_table(
        index="date", columns="name", values="price_avg" if "price_avg" in subset.columns else "price_max", aggfunc="mean"
    )

    corr = pivot.corr()

    fig, ax = plt.subplots(figsize=(12, 10))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdYlBu_r",
                square=True, ax=ax, vmin=-1, vmax=1,
                annot_kws={"size": 7})
    ax.set_title("Price Correlation Between Commodities", fontsize=13)
    ax.tick_params(axis="both", labelsize=7)
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "correlation_matrix.png", bbox_inches="tight")
    plt.close()
    print(f"Saved: {PLOTS_DIR / 'correlation_matrix.png'}")


def main():
    parser = argparse.ArgumentParser(description="Generate visualizations")
    parser.add_argument("--all", action="store_true", help="Generate all plots")
    parser.add_argument("--history", action="store_true", help="Price history plots")
    parser.add_argument("--forecasts", action="store_true", help="Forecast plots")
    parser.add_argument("--compare", action="store_true", help="Model comparison")
    parser.add_argument("--correlation", action="store_true", help="Correlation matrix")
    args = parser.parse_args()

    clean_csv = DATA_DIR / "all_prices_clean.csv"
    results_csv = OUTPUTS_DIR / "model_results.csv"
    forecasts_csv = OUTPUTS_DIR / "forecasts.csv"

    if args.all or args.history:
        if clean_csv.exists():
            plot_commodity_history(clean_csv)
        else:
            print(f"Clean data not found: {clean_csv}")

    if args.all or args.correlation:
        if clean_csv.exists():
            plot_correlation_matrix(clean_csv)

    if args.all or args.compare:
        if results_csv.exists():
            plot_model_comparison(results_csv)
        else:
            print(f"Results not found: {results_csv}")

    if args.all or args.forecasts:
        if forecasts_csv.exists() and clean_csv.exists():
            plot_forecasts(forecasts_csv, clean_csv)
        else:
            print(f"Forecasts not found: {forecasts_csv}")


if __name__ == "__main__":
    main()
