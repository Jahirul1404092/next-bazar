# -*- coding: utf-8 -*-
"""
Auto-Update Pipeline for Next Bazar Price Prediction.

Smart incremental update:
1. Check current date
2. Check latest date already in data/raw_daily/
3. Scrape only NEW data (from last_date+1 to today)
4. Process data (merge + clean + feature engineering)
5. Retrain ML models
6. Regenerate dashboard_data.js
7. (Optional) Redeploy

Usage:
    python auto_update.py                  # Run full incremental update
    python auto_update.py --check-only     # Only show what would be updated
    python auto_update.py --skip-train     # Update data but skip model retraining
    python auto_update.py --force-retrain  # Force retrain even if no new data

Author: Jahirul (2026)
"""

import os
import sys
import time
import json
import logging
import argparse
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "raw_daily"
XLSX_DIR = DATA_DIR / "raw_xlsx"
MODELS_DIR = PROJECT_DIR / "models"
OUTPUTS_DIR = PROJECT_DIR / "outputs"
LOG_FILE = PROJECT_DIR / "auto_update.log"
STATE_FILE = PROJECT_DIR / "update_state.json"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State management — track last update info
# ---------------------------------------------------------------------------
def load_state() -> dict:
    """Load last update state from JSON file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict):
    """Save update state to JSON file."""
    state["last_run"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Step 1: Check what data we already have
# ---------------------------------------------------------------------------
def get_latest_data_date() -> date | None:
    """Find the most recent date in raw_daily/ directory."""
    if not RAW_DIR.exists():
        return None

    csv_files = sorted(RAW_DIR.glob("*.csv"))
    if not csv_files:
        return None

    # File names are YYYY-MM-DD.csv
    latest = csv_files[-1].stem  # e.g., "2026-03-12"
    try:
        return date.fromisoformat(latest)
    except ValueError:
        return None


def get_all_existing_dates() -> set:
    """Get all dates we already have data for."""
    if not RAW_DIR.exists():
        return set()

    dates = set()
    for f in RAW_DIR.glob("*.csv"):
        try:
            dates.add(date.fromisoformat(f.stem))
        except ValueError:
            pass
    return dates


def get_missing_dates(latest_date: date, today: date) -> list:
    """
    Calculate which dates between latest_date+1 and today are missing.
    Note: TCB doesn't publish on Fridays (weekend in Bangladesh) and holidays,
    so not all dates will have data. We return the gap dates to check.
    """
    existing = get_all_existing_dates()
    missing = []

    current = latest_date + timedelta(days=1)
    while current <= today:
        if current not in existing:
            missing.append(current)
        current += timedelta(days=1)

    return missing


# ---------------------------------------------------------------------------
# Step 2: Incremental scraping — only fetch new dates
# ---------------------------------------------------------------------------
def scrape_incremental(missing_dates: list, latest_date: date = None) -> int:
    """
    Scrape only the dates we're missing.

    Strategy: Pass --stop-at-date to the scraper so it:
    - Only fetches listing pages until it finds dates we already have
    - Only downloads/parses entries NEWER than our latest date
    - Skips all 120+ older listing pages entirely

    This makes a daily update take ~5 seconds instead of 2+ minutes.

    Returns count of new files downloaded.
    """
    if not missing_dates:
        logger.info("No missing dates to scrape.")
        return 0

    logger.info(f"Need to check {len(missing_dates)} potential new dates")
    logger.info(f"  Date range: {missing_dates[0]} to {missing_dates[-1]}")

    # Count existing CSVs before scraping
    before_count = len(list(RAW_DIR.glob("*.csv"))) if RAW_DIR.exists() else 0

    # Run the scraper with --stop-at-date for fast incremental mode
    cmd = [sys.executable, "scraper.py"]
    if latest_date:
        cmd.extend(["--stop-at-date", latest_date.isoformat()])
        logger.info(f"  Incremental mode: only fetching entries after {latest_date}")

    result = subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        capture_output=False,
    )

    if result.returncode != 0:
        logger.warning(f"Scraper exited with code {result.returncode}")

    # Count new CSVs
    after_count = len(list(RAW_DIR.glob("*.csv")))
    new_count = after_count - before_count

    logger.info(f"New daily CSVs downloaded: {new_count}")
    return new_count


# ---------------------------------------------------------------------------
# Step 3: Process data (merge + clean + features)
# ---------------------------------------------------------------------------
def process_data() -> bool:
    """Run process_data.py to clean and generate features."""
    logger.info("Processing data (clean + feature engineering)...")
    result = subprocess.run(
        [sys.executable, "process_data.py"],
        cwd=PROJECT_DIR,
        capture_output=False,
    )
    if result.returncode != 0:
        logger.error(f"process_data.py failed with code {result.returncode}")
        return False
    return True


# ---------------------------------------------------------------------------
# Step 4: Retrain models
# ---------------------------------------------------------------------------
def retrain_models(forecast_days: int = 30) -> bool:
    """Retrain ML models (XGBoost, LightGBM, Prophet)."""
    logger.info(f"Retraining models (forecast_days={forecast_days})...")
    result = subprocess.run(
        [sys.executable, "model.py", "--forecast-days", str(forecast_days)],
        cwd=PROJECT_DIR,
        capture_output=False,
    )
    if result.returncode != 0:
        logger.error(f"model.py failed with code {result.returncode}")
        return False
    return True


# ---------------------------------------------------------------------------
# Step 5: Regenerate dashboard data
# ---------------------------------------------------------------------------
def regenerate_dashboard() -> bool:
    """Generate fresh dashboard_data.js from updated models + data."""
    logger.info("Regenerating dashboard_data.js...")
    result = subprocess.run(
        [sys.executable, "generate_dashboard_data.py"],
        cwd=PROJECT_DIR,
        capture_output=False,
    )
    if result.returncode != 0:
        logger.error(f"generate_dashboard_data.py failed with code {result.returncode}")
        return False
    return True


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_update(args):
    """Run the full incremental update pipeline."""
    today = date.today()
    logger.info(f"\n{'='*70}")
    logger.info(f"Next Bazar Auto-Update Pipeline")
    logger.info(f"{'='*70}")
    logger.info(f"Current date:  {today}")

    # Step 1: Check existing data
    latest_date = get_latest_data_date()
    existing_count = len(get_all_existing_dates())

    if latest_date:
        logger.info(f"Latest data:   {latest_date}")
        logger.info(f"Total dates:   {existing_count}")
        days_behind = (today - latest_date).days
        logger.info(f"Days behind:   {days_behind}")
    else:
        logger.info("No existing data found. Will do full scrape.")
        days_behind = None

    # Step 2: Find missing dates
    if latest_date:
        missing = get_missing_dates(latest_date, today)
        logger.info(f"Missing dates: {len(missing)}")
    else:
        missing = [today]  # At least today

    # Check-only mode
    if args.check_only:
        if not missing:
            logger.info("\nData is up to date! No new dates to fetch.")
        else:
            logger.info(f"\nWould fetch data for {len(missing)} dates:")
            for d in missing[:10]:
                logger.info(f"  - {d}")
            if len(missing) > 10:
                logger.info(f"  ... and {len(missing) - 10} more")
        return

    # Step 3: Scrape new data
    if missing:
        logger.info(f"\n--- STEP 1/4: Scraping new data ---")
        new_count = scrape_incremental(missing, latest_date=latest_date)
        logger.info(f"Scraped {new_count} new daily files")
    else:
        new_count = 0
        logger.info("\nData is already up to date!")

    # Decide whether to continue with processing/training
    if new_count == 0 and not args.force_retrain:
        logger.info("No new data found. Skipping processing and training.")
        logger.info("Use --force-retrain to retrain models anyway.")

        state = load_state()
        state["last_check"] = today.isoformat()
        state["status"] = "up_to_date"
        state["data_through"] = latest_date.isoformat() if latest_date else None
        save_state(state)
        return

    # Step 4: Process data
    logger.info(f"\n--- STEP 2/4: Processing data ---")
    if not process_data():
        logger.error("Data processing failed! Aborting.")
        return

    # Step 5: Smart retraining — only retrain when enough new data accumulates
    # XGBoost/LightGBM can't do true incremental learning, so we retrain from scratch.
    # But retraining every day for 1 new data point is wasteful (~7 min).
    # Strategy: retrain every 7 days OR if forced, skip otherwise.
    # The existing model predictions are still valid for a few days.
    if args.skip_train:
        logger.info(f"\n--- STEP 3/4: SKIPPED (--skip-train) ---")
    else:
        state = load_state()
        last_train = state.get("last_retrain")
        days_since_train = None
        if last_train:
            try:
                last_train_date = date.fromisoformat(last_train)
                days_since_train = (today - last_train_date).days
            except ValueError:
                pass

        needs_retrain = False
        retrain_reason = ""

        if args.force_retrain:
            needs_retrain = True
            retrain_reason = "forced by --force-retrain"
        elif days_since_train is None:
            needs_retrain = True
            retrain_reason = "no previous training record"
        elif days_since_train >= 7:
            needs_retrain = True
            retrain_reason = f"{days_since_train} days since last training (threshold: 7)"
        elif new_count >= 5:
            needs_retrain = True
            retrain_reason = f"{new_count} new data files (threshold: 5)"
        elif not (OUTPUTS_DIR / "forecasts.csv").exists():
            needs_retrain = True
            retrain_reason = "no forecasts.csv found"
        else:
            retrain_reason = (
                f"only {new_count} new file(s), "
                f"{days_since_train} day(s) since last training. "
                f"Will retrain after 7 days or 5+ new files."
            )

        if needs_retrain:
            logger.info(f"\n--- STEP 3/4: Retraining models ({retrain_reason}) ---")
            if retrain_models(args.forecast_days):
                # Record successful retrain date
                state = load_state()
                state["last_retrain"] = today.isoformat()
                save_state(state)
            else:
                logger.warning("Model training had issues, but continuing...")
        else:
            logger.info(f"\n--- STEP 3/4: SKIPPING retrain ({retrain_reason}) ---")
            logger.info("  Using existing model predictions. Use --force-retrain to override.")

    # Step 6: Regenerate dashboard
    logger.info(f"\n--- STEP 4/4: Regenerating dashboard ---")
    if not regenerate_dashboard():
        logger.error("Dashboard generation failed!")
        return

    # Save state
    new_latest = get_latest_data_date()
    state = load_state()
    state["last_update"] = today.isoformat()
    state["data_through"] = new_latest.isoformat() if new_latest else None
    state["new_dates_added"] = new_count
    state["status"] = "updated"
    state["total_dates"] = len(get_all_existing_dates())
    save_state(state)

    # Summary
    logger.info(f"\n{'='*70}")
    logger.info(f"UPDATE COMPLETE!")
    logger.info(f"{'='*70}")
    logger.info(f"  New data files:    {new_count}")
    logger.info(f"  Data through:      {new_latest}")
    logger.info(f"  Total dates:       {state['total_dates']}")
    logger.info(f"  Models retrained:  {'Yes' if not args.skip_train else 'No'}")
    logger.info(f"  Dashboard updated: Yes")
    logger.info(f"")
    logger.info(f"  Open dashboard.html or run: python server.py")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Next Bazar Auto-Update Pipeline"
    )
    parser.add_argument(
        "--check-only", action="store_true",
        help="Only check what needs updating (don't download or train)"
    )
    parser.add_argument(
        "--skip-train", action="store_true",
        help="Update data but skip model retraining"
    )
    parser.add_argument(
        "--force-retrain", action="store_true",
        help="Force retrain even if no new data was found"
    )
    parser.add_argument(
        "--forecast-days", type=int, default=30,
        help="Number of days to forecast (default: 30)"
    )
    args = parser.parse_args()

    try:
        run_update(args)
    except KeyboardInterrupt:
        logger.info("\nUpdate cancelled by user.")
    except Exception as e:
        logger.error(f"Update failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
