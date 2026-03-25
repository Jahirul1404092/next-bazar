# -*- coding: utf-8 -*-
"""
Data Processing Pipeline for Next Bazar price data.

Handles:
1. Loading raw scraped CSV data (and optionally legacy Excel files)
2. Cleaning: parse Bengali numerals, handle NA/missing, normalize names
3. Feature engineering: lags, rolling means, seasonality, trend
4. Output: clean per-commodity time-series CSVs ready for modeling

Author: Jahirul (2026)
"""

import os
import re
import sys
import logging
import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):
        return iterable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
RAW_MERGED = DATA_DIR / "all_prices_raw.csv"
LEGACY_DIR = PROJECT_DIR.parent / "New folder"  # Your old Excel files
CLEAN_FILE = DATA_DIR / "all_prices_clean.csv"
FEATURES_DIR = DATA_DIR / "features"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bengali numeral conversion
# ---------------------------------------------------------------------------
BANGLA_DIGITS = {"০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4",
                 "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9"}


def bangla_to_english(text: str) -> str:
    """Convert Bengali digits to English digits."""
    if not isinstance(text, str):
        return str(text)
    for bn, en in BANGLA_DIGITS.items():
        text = text.replace(bn, en)
    return text


def parse_price(value) -> Optional[float]:
    """Parse a price value that may be in Bengali, have (+)/(-) signs, or be 'NA'."""
    if pd.isna(value):
        return np.nan

    s = str(value).strip()

    if s.upper() in ("NA", "N/A", "-", "", "—", "–"):
        return np.nan

    # Convert Bengali digits
    s = bangla_to_english(s)

    # Handle change columns: "(+) 1.82" or "(-) 0.5" or "0"
    s = s.replace("(+)", "").replace("(-)", "-").strip()

    # Remove commas from large numbers
    s = s.replace(",", "")

    # Remove any remaining non-numeric chars except . and -
    s = re.sub(r"[^\d.\-]", "", s)

    try:
        return float(s)
    except (ValueError, TypeError):
        return np.nan


# ---------------------------------------------------------------------------
# Load legacy Excel data (your 2018–2021 files)
# ---------------------------------------------------------------------------

def load_legacy_excel(file_path: Path) -> pd.DataFrame:
    """Load one of the legacy multi-sheet Excel files into a single DataFrame."""
    logger.info(f"Loading legacy file: {file_path.name}")

    xl = pd.ExcelFile(file_path, engine="openpyxl")
    dfs = []

    for sheet_name in tqdm(xl.sheet_names, desc=f"Reading {file_path.name}"):
        try:
            df = xl.parse(sheet_name)
        except Exception:
            continue

        if df.empty or len(df.columns) < 10:
            continue

        # The first column is the index from original to_excel(), skip it
        if "Unnamed: 0" in df.columns:
            df = df.drop(columns=["Unnamed: 0"])

        # Parse date from sheet name: "2021_3_1" -> "2021-03-01"
        parts = sheet_name.split("_")
        if len(parts) == 3:
            try:
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                dt = pd.Timestamp(year=year, month=month, day=day)
                df["date"] = dt.isoformat()[:10]
            except (ValueError, IndexError):
                continue
        else:
            continue

        # Standardize column names
        col_map = {
            "name": "name",
            "unit": "unit",
            "tcbtoday": "tcb_today",
            "localtoday": "local_today",
            "tcboneweekago": "tcb_1week_ago",
            "localoneweekago": "local_1week_ago",
            "tcbonemonthago": "tcb_1month_ago",
            "localonemonthago": "local_1month_ago",
            "changeinmonth": "change_month",
            "tcboneyearago": "tcb_1year_ago",
            "localoneyearago": "local_1year_ago",
            "changeinoneyear": "change_year",
            "found": "found",
        }
        df = df.rename(columns=col_map)

        # Keep only expected columns
        expected = list(col_map.values()) + ["date"]
        df = df[[c for c in expected if c in df.columns]]

        dfs.append(df)

    if dfs:
        result = pd.concat(dfs, ignore_index=True)
        logger.info(f"  Loaded {len(result)} rows from {len(dfs)} sheets")
        return result
    return pd.DataFrame()


def load_all_legacy() -> pd.DataFrame:
    """Load all legacy Excel files from the New folder."""
    legacy_files = [
        LEGACY_DIR / "price18_01_01.xlsx",
        LEGACY_DIR / "price19_21.xlsx",
    ]

    dfs = []
    for f in legacy_files:
        if f.exists():
            df = load_legacy_excel(f)
            if len(df) > 0:
                dfs.append(df)

    if dfs:
        result = pd.concat(dfs, ignore_index=True)
        # Drop rows where 'found' == 'n' (placeholder copies)
        if "found" in result.columns:
            result = result[result["found"] != "n"]
            result = result.drop(columns=["found"], errors="ignore")
        return result

    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

def unify_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Unify columns from different data formats into a common schema.

    Legacy format: tcb_today, local_today, tcb_1week_ago, local_1week_ago, ...
    New format:    today_min, today_max, week_min, week_max, ...

    Unified schema:
      price_min, price_max  (today's min/max retail prices)
      week_min, week_max    (1 week ago)
      month_min, month_max  (1 month ago)
      month_change          (% change over month)
      year_min, year_max    (1 year ago)
      year_change           (% change over year)
    """
    df = df.copy()

    # Detect format by checking which columns exist
    has_legacy = "tcb_today" in df.columns or "local_today" in df.columns
    has_new = "today_min" in df.columns or "today_max" in df.columns

    if has_legacy and not has_new:
        # Legacy format: map tcb→min, local→max (rough equivalence)
        renames = {
            "tcb_today": "price_min", "local_today": "price_max",
            "tcb_1week_ago": "week_min", "local_1week_ago": "week_max",
            "tcb_1month_ago": "month_min", "local_1month_ago": "month_max",
            "change_month": "month_change",
            "tcb_1year_ago": "year_min", "local_1year_ago": "year_max",
            "change_year": "year_change",
        }
        df = df.rename(columns=renames)
    elif has_new and not has_legacy:
        # New format: already has the right names (just ensure consistency)
        renames = {
            "today_min": "price_min", "today_max": "price_max",
        }
        df = df.rename(columns=renames)

    return df


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the raw concatenated data:
    - Unify columns from legacy/new formats
    - Parse prices to float
    - Normalize commodity names
    - Compute price_avg as primary modeling target
    - Remove duplicates
    - Sort by date
    """
    logger.info(f"Cleaning {len(df)} rows...")

    df = df.copy()

    # Parse date
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    # Parse all price columns to float
    price_cols = [
        "price_min", "price_max",
        "week_min", "week_max",
        "month_min", "month_max",
        "month_change",
        "year_min", "year_max",
        "year_change",
    ]
    for col in price_cols:
        if col in df.columns:
            df[col] = df[col].apply(parse_price)

    # Normalize commodity names (strip whitespace, collapse spaces)
    df["name"] = df["name"].astype(str).str.strip()
    df["name"] = df["name"].str.replace(r"\s+", " ", regex=True)

    # Remove rows with no name or no price data at all
    df = df[df["name"].str.len() > 1]
    df = df.dropna(subset=["price_min", "price_max"], how="all")

    # Compute average price as primary modeling target
    df["price_avg"] = df[["price_min", "price_max"]].mean(axis=1)

    # Remove exact duplicates
    df = df.drop_duplicates(subset=["date", "name"], keep="last")

    # Sort
    df = df.sort_values(["name", "date"]).reset_index(drop=True)

    logger.info(f"After cleaning: {len(df)} rows, {df['name'].nunique()} commodities, "
                f"{df['date'].nunique()} dates")

    return df


# ---------------------------------------------------------------------------
# Feature Engineering
# ---------------------------------------------------------------------------

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create features for ML modeling per commodity time series:
    - Lag features (1, 7, 14, 30 days)
    - Rolling mean/std (7, 14, 30 days)
    - Day of week, month, year
    - Price velocity and acceleration
    - Seasonal decomposition features
    """
    logger.info("Engineering features...")

    df = df.copy()
    df = df.sort_values(["name", "date"]).reset_index(drop=True)

    # Primary target: price_avg (average of min/max retail prices)
    # Also track price_min and price_max separately
    df["price"] = df["price_avg"]

    # Fill gaps within each commodity using forward fill (up to 7 days)
    all_features = []

    for commodity, group in tqdm(df.groupby("name"), desc="Feature engineering"):
        g = group.copy()
        g = g.set_index("date")

        # Reindex to daily frequency to expose gaps
        date_range = pd.date_range(g.index.min(), g.index.max(), freq="D")
        g = g.reindex(date_range)
        g["name"] = commodity
        g.index.name = "date"

        # Forward fill prices (up to 7 days gap)
        for col in ["price", "price_min", "price_max"]:
            if col in g.columns:
                g[col] = g[col].ffill(limit=7)

        # Drop rows still missing price
        g = g.dropna(subset=["price"])

        if len(g) < 30:
            continue

        # ----- Lag features -----
        for lag in [1, 2, 3, 7, 14, 30]:
            g[f"price_lag_{lag}"] = g["price"].shift(lag)

        # ----- Rolling statistics -----
        for window in [7, 14, 30, 60]:
            g[f"price_rolling_mean_{window}"] = g["price"].rolling(window, min_periods=1).mean()
            g[f"price_rolling_std_{window}"] = g["price"].rolling(window, min_periods=1).std()
            g[f"price_rolling_min_{window}"] = g["price"].rolling(window, min_periods=1).min()
            g[f"price_rolling_max_{window}"] = g["price"].rolling(window, min_periods=1).max()

        # ----- Price change features -----
        g["price_diff_1"] = g["price"].diff(1)
        g["price_diff_7"] = g["price"].diff(7)
        g["price_diff_30"] = g["price"].diff(30)
        g["price_pct_change_1"] = g["price"].pct_change(1)
        g["price_pct_change_7"] = g["price"].pct_change(7)
        g["price_pct_change_30"] = g["price"].pct_change(30)

        # ----- Acceleration (diff of diff) -----
        g["price_accel"] = g["price_diff_1"].diff(1)

        # ----- Calendar features -----
        g["day_of_week"] = g.index.dayofweek
        g["day_of_month"] = g.index.day
        g["month"] = g.index.month
        g["year"] = g.index.year
        g["week_of_year"] = g.index.isocalendar().week.astype(int)
        g["is_weekend"] = (g.index.dayofweek >= 5).astype(int)

        # ----- Ramadan approximation (rough — shifts yearly) -----
        g["quarter"] = g.index.quarter

        # ----- Price spread (max - min) -----
        if "price_min" in g.columns and "price_max" in g.columns:
            g["price_spread"] = g["price_max"] - g["price_min"]
            g["price_spread_pct"] = g["price_spread"] / g["price"].replace(0, np.nan)

        # ----- Volatility -----
        g["volatility_7"] = g["price_pct_change_1"].rolling(7, min_periods=1).std()
        g["volatility_30"] = g["price_pct_change_1"].rolling(30, min_periods=1).std()

        # ----- Trend (linear regression slope over 30 days) -----
        g["trend_30"] = (
            g["price"]
            .rolling(30, min_periods=15)
            .apply(lambda x: np.polyfit(range(len(x)), x, 1)[0], raw=True)
        )

        g = g.reset_index()
        all_features.append(g)

    if not all_features:
        logger.error("No features generated!")
        return pd.DataFrame()

    result = pd.concat(all_features, ignore_index=True)
    logger.info(f"Features generated: {len(result)} rows, {result.columns.size} columns")

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Process Next Bazar data")
    parser.add_argument(
        "--legacy-only", action="store_true",
        help="Only process legacy Excel files (no scraped CSVs)"
    )
    parser.add_argument(
        "--scraped-only", action="store_true",
        help="Only process scraped CSV data (no legacy Excel)"
    )
    parser.add_argument(
        "--skip-features", action="store_true",
        help="Skip feature engineering step"
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Load data
    dfs = []

    if not args.scraped_only:
        logger.info("=" * 60)
        logger.info("Loading legacy Excel data...")
        legacy = load_all_legacy()
        if len(legacy) > 0:
            dfs.append(legacy)
            logger.info(f"Legacy data: {len(legacy)} rows")

    if not args.legacy_only:
        scraped_loaded = False
        if RAW_MERGED.exists():
            logger.info("=" * 60)
            logger.info("Loading merged scraped CSV data...")
            scraped = pd.read_csv(RAW_MERGED, encoding="utf-8-sig")
            if len(scraped) > 0:
                dfs.append(scraped)
                logger.info(f"Scraped data (merged): {len(scraped)} rows")
                scraped_loaded = True

        # Also load individual daily CSVs in case merge hasn't been run
        raw_daily_dir = DATA_DIR / "raw_daily"
        if raw_daily_dir.exists():
            csv_files = sorted(raw_daily_dir.glob("*.csv"))
            if csv_files and not scraped_loaded:
                logger.info("=" * 60)
                logger.info(f"Loading {len(csv_files)} daily CSV files...")
                daily_dfs = []
                for f in csv_files:
                    try:
                        d = pd.read_csv(f, encoding="utf-8-sig")
                        if len(d) > 0:
                            daily_dfs.append(d)
                    except Exception:
                        pass
                if daily_dfs:
                    scraped = pd.concat(daily_dfs, ignore_index=True)
                    dfs.append(scraped)
                    logger.info(f"Scraped data (daily): {len(scraped)} rows")
                    scraped_loaded = True

        if not scraped_loaded:
            logger.warning(f"No scraped data found.")
            logger.warning("Run scraper.py first, or use --legacy-only")

    if not dfs:
        logger.error("No data loaded!")
        return

    # Unify columns for each source before combining
    unified_dfs = []
    for d in dfs:
        unified_dfs.append(unify_columns(d))
    combined = pd.concat(unified_dfs, ignore_index=True)
    logger.info(f"\nCombined raw data: {len(combined)} rows")

    # Step 2: Clean
    logger.info("=" * 60)
    clean = clean_data(combined)
    clean.to_csv(CLEAN_FILE, index=False, encoding="utf-8-sig")
    logger.info(f"Clean data saved to {CLEAN_FILE}")

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("COMMODITY SUMMARY:")
    summary = (
        clean.groupby("name")
        .agg(
            days=("date", "nunique"),
            min_date=("date", "min"),
            max_date=("date", "max"),
            avg_price=("price_avg", "mean"),
            avg_min=("price_min", "mean"),
            avg_max=("price_max", "mean"),
        )
        .sort_values("days", ascending=False)
    )
    try:
        print(summary.to_string())
    except UnicodeEncodeError:
        # Windows console may not support Bengali — save to file instead
        summary.to_csv(DATA_DIR / "commodity_summary.csv", encoding="utf-8-sig")
        logger.info(f"Summary saved to {DATA_DIR / 'commodity_summary.csv'} (console encoding issue)")

    # Step 3: Feature engineering
    if not args.skip_features:
        logger.info("\n" + "=" * 60)
        features = engineer_features(clean)

        if len(features) > 0:
            # Save combined
            features_file = DATA_DIR / "all_features.csv"
            features.to_csv(features_file, index=False, encoding="utf-8-sig")
            logger.info(f"All features saved to {features_file}")

            # Save per-commodity for easy modeling
            for commodity, group in features.groupby("name"):
                safe_name = re.sub(r'[^\w\s]', '', commodity)[:50].strip().replace(' ', '_')
                out_path = FEATURES_DIR / f"{safe_name}.csv"
                group.to_csv(out_path, index=False, encoding="utf-8-sig")

            logger.info(f"Per-commodity features saved to {FEATURES_DIR}/")

    logger.info("\nDone! Data is ready for modeling.")


if __name__ == "__main__":
    main()
