# -*- coding: utf-8 -*-
"""
Main runner for the Next Bazar Price Prediction pipeline.

Usage:
    python run.py --full          # Run entire pipeline (scrape -> process -> model -> visualize)
    python run.py --test          # Test scraper on 3 sample files
    python run.py --scrape-only   # Only scrape data from tcb.gov.bd
    python run.py --process-only  # Only process existing data (legacy Excel + scraped)
    python run.py --model-only    # Only run modeling (data must exist)
    python run.py --viz-only      # Only generate visualizations
    python run.py --legacy-only   # Process legacy Excel only (no scraping)
    python run.py --dashboard     # Generate dashboard data from existing models
    python run.py --update        # Smart incremental update (scrape new + retrain + dashboard)
    python run.py --check         # Check what new data is available
    python run.py --serve         # Start web server on port 5000

Author: Jahirul (2026)
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent


def run_cmd(cmd: list, desc: str):
    """Run a command and print output."""
    print(f"\n{'='*70}")
    print(f"STEP: {desc}")
    print(f"{'='*70}\n")
    result = subprocess.run(
        [sys.executable] + cmd,
        cwd=PROJECT_DIR,
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"\nWARNING: {desc} exited with code {result.returncode}")
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Next Bazar Pipeline Runner")
    parser.add_argument("--full", action="store_true", help="Full pipeline")
    parser.add_argument("--test", action="store_true", help="Test scraper only")
    parser.add_argument("--scrape-only", action="store_true", help="Scrape only")
    parser.add_argument("--process-only", action="store_true", help="Process data only")
    parser.add_argument("--model-only", action="store_true", help="Train models only")
    parser.add_argument("--viz-only", action="store_true", help="Visualize only")
    parser.add_argument("--legacy-only", action="store_true",
                        help="Process legacy Excel only (no scraping)")
    parser.add_argument("--dashboard", action="store_true",
                        help="Generate dashboard_data.js from existing data/forecasts")
    parser.add_argument("--serve", action="store_true",
                        help="Start web server on port 5000")
    parser.add_argument("--update", action="store_true",
                        help="Smart incremental update: scrape new data, retrain, regenerate dashboard")
    parser.add_argument("--check", action="store_true",
                        help="Check what new data is available without downloading")
    parser.add_argument("--forecast-days", type=int, default=30)

    args = parser.parse_args()

    if args.test:
        run_cmd(["scraper.py", "--test"], "Testing scraper with 3 sample files")
        return

    if args.check:
        run_cmd(["auto_update.py", "--check-only"], "Checking for new data")
        return

    if args.update:
        cmd = ["auto_update.py", "--forecast-days", str(args.forecast_days)]
        run_cmd(cmd, "Smart incremental update (scrape + process + train + dashboard)")
        return

    if args.full or args.scrape_only:
        run_cmd(["scraper.py"], "Scraping price data from tcb.gov.bd")
        if args.scrape_only:
            return

    if args.full or args.process_only or args.legacy_only:
        cmd = ["process_data.py"]
        if args.legacy_only:
            cmd.append("--legacy-only")
        run_cmd(cmd, "Processing and cleaning data")
        if args.process_only:
            return

    if args.full or args.model_only:
        run_cmd(
            ["model.py", "--forecast-days", str(args.forecast_days)],
            "Training prediction models"
        )
        if args.model_only:
            return

    if args.full or args.viz_only:
        run_cmd(["visualize.py", "--all"], "Generating visualizations")

    if args.full or args.dashboard:
        run_cmd(["generate_dashboard_data.py"], "Generating dashboard data (dashboard_data.js)")
        if args.dashboard:
            return

    if args.serve:
        print(f"\n{'='*70}")
        print("Starting web server...")
        print(f"{'='*70}\n")
        run_cmd(["server.py"], "Web server on http://localhost:5000")
        return

    if args.full:
        print(f"\n{'='*70}")
        print("PIPELINE COMPLETE!")
        print(f"{'='*70}")
        print(f"\nOutputs:")
        print(f"  Clean data:     data/all_prices_clean.csv")
        print(f"  Features:       data/features/*.csv")
        print(f"  Models:         models/*.pkl")
        print(f"  Results:        outputs/model_results.csv")
        print(f"  Forecasts:      outputs/forecasts.csv")
        print(f"  Dashboard data: dashboard_data.js")
        print(f"  Plots:          outputs/plots/*.png")
        print(f"\nOpen dashboard.html or run: python run.py --serve")


if __name__ == "__main__":
    main()
