# -*- coding: utf-8 -*-
"""
Generate dashboard_data.js from real price data and model predictions.

This script reads the clean price data + model forecasts and generates
a JavaScript file that the dashboard.html can load directly.

Usage:
    python generate_dashboard_data.py

Requires:
    - data/all_prices_clean.csv  (from process_data.py)
    - outputs/forecasts.csv      (from model.py — optional, uses last-value if missing)
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUTS_DIR = PROJECT_DIR / "outputs"
CLEAN_FILE = DATA_DIR / "all_prices_clean.csv"
FORECASTS_FILE = OUTPUTS_DIR / "forecasts.csv"
DASHBOARD_DATA_JS = PROJECT_DIR / "dashboard_data.js"

# English names for commodities (Bengali → English mapping)
# This maps the Bengali commodity names from TCB to readable English names
EN_NAMES = {
    "চাল সরু (নাজির/মিনিকেট)": "Fine Rice (Nazir/Miniket)",
    "চাল (মোটা)/স্বর্ণা": "Coarse Rice",
    "আটা সাদা (খোলা)": "Flour (Loose)",
    "আটা (প্যাকেট)": "Flour (Packet)",
    "ময়দা (খোলা)": "Maida (Loose)",
    "সয়াবিন তেল (লুজ)": "Soybean Oil (Loose)",
    "সয়াবিন তেল (বোতল)": "Soybean Oil (Bottle)",
    "পাম অয়েল (লুজ)": "Palm Oil (Loose)",
    "মশুর ডাল (বড়)": "Red Lentil (Large)",
    "মশুর ডাল (ছোট)": "Red Lentil (Small)",
    "মুগ ডাল": "Mung Dal",
    "ছোলা": "Chickpea",
    "আলু": "Potato",
    "আলু (নতুন)": "Potato (New)",
    "পিঁয়াজ (দেশী)": "Onion (Local)",
    "পিঁয়াজ (আমদানি)": "Onion (Imported)",
    "রসুন (দেশী)": "Garlic (Local)",
    "রসুন (আমদানি)": "Garlic (Imported)",
    "শুকনা মরিচ (দেশী)": "Dry Chili (Local)",
    "হলুদ (দেশী)": "Turmeric (Local)",
    "আদা (দেশী)": "Ginger (Local)",
    "আদা (আমদানি)": "Ginger (Imported)",
    "জিরা": "Cumin",
    "দারুচিনি": "Cinnamon",
    "এলাচ": "Cardamom",
    "এলাচ(ছোট)": "Cardamom (Small)",
    "চিনি": "Sugar",
    "লবণ": "Salt (Iodized)",
    "গুড়": "Jaggery",
    "রুই মাছ": "Rohu Fish",
    "ইলিশ": "Hilsa Fish",
    "গরুর মাংস": "Beef",
    "খাসীর মাংস": "Mutton",
    "মুরগী (ব্রয়লার)": "Chicken (Broiler)",
    "মুরগী (দেশী)": "Chicken (Local)",
    "ডিম (ফার্ম)": "Egg (Farm)",
    "ডিম (দেশী)": "Egg (Local)",
    "গুঁড়া দুধ (ডানো)": "Milk Powder (Dano)",
    "কাঁচামরিচ": "Green Chili",
    "বেগুন": "Eggplant",
    "লেবু": "Lemon",
    "শসা": "Cucumber",
    "টমেটো": "Tomato",
    "খেজুর(সাধারণ মানের)": "Dates (Regular)",
    "খেজুর": "Dates",
    "এম.এস রড (৬০ গ্রেড)": "MS Rod (Grade 60)",
    "এম.এস রড (৪০ গ্রেড)": "MS Rod (Grade 40)",
    "সিমেন্ট": "Cement",
    "এ,কে,র ডাল": "AKR Dal",
    "খস": "Poppy Seed",
}


def get_unit(name):
    """Guess unit from commodity name."""
    name_lower = name.lower()
    if "তেল" in name and "বোতল" in name:
        return "5L"
    if "তেল" in name or "অয়েল" in name:
        return "per L"
    if "ডিম" in name:
        return "per hali"
    if "রড" in name or "সিমেন্ট" in name:
        return "per MT"
    if "দুধ" in name and "গুঁড়া" in name:
        return "1 kg"
    return "per kg"


def main():
    print("=" * 60)
    print("Generating dashboard_data.js from real data")
    print("=" * 60)

    # Load clean price data
    if not CLEAN_FILE.exists():
        print(f"ERROR: Clean data not found: {CLEAN_FILE}")
        print("Run process_data.py first!")
        sys.exit(1)

    df = pd.read_csv(CLEAN_FILE, parse_dates=["date"])
    # Filter out bad dates (before 2018 — TCB data starts Aug 2018)
    df = df[df["date"] >= "2018-01-01"].copy()
    # Filter out future dates (TCB sometimes posts data with future dates)
    today_dt = pd.Timestamp.now().normalize()
    future_count = (df["date"] > today_dt).sum()
    if future_count > 0:
        print(f"WARNING: Removing {future_count} rows with future dates (after {today_dt.strftime('%Y-%m-%d')})")
        df = df[df["date"] <= today_dt].copy()
    print(f"Loaded {len(df)} rows, {df['name'].nunique()} commodities")

    # Load forecasts if available
    has_forecasts = False
    forecasts = {}
    if FORECASTS_FILE.exists():
        fc_df = pd.read_csv(FORECASTS_FILE, parse_dates=["date"])
        has_forecasts = True
        print(f"Loaded {len(fc_df)} forecast rows")

        # Pick best model per commodity (lowest predicted price variance = most stable)
        for commodity, group in fc_df.groupby("commodity"):
            # If multiple models, pick xgboost, then lightgbm, then first available
            models = group["model"].unique()
            if "xgboost" in models:
                best = group[group["model"] == "xgboost"]
            elif "lightgbm" in models:
                best = group[group["model"] == "lightgbm"]
            else:
                best = group[group["model"] == models[0]]
            forecasts[commodity] = best.sort_values("date")
    else:
        print("No forecasts file found — will generate simple trend-based predictions")

    # Build commodity list and data
    today = df["date"].max()
    commodities_js = []
    data_js = {}

    # Get commodities with enough data (at least 60 days)
    commodity_counts = df.groupby("name")["date"].nunique()
    valid_commodities = commodity_counts[commodity_counts >= 60].index.tolist()
    print(f"Using {len(valid_commodities)} commodities with >= 60 days of data")

    for name in sorted(valid_commodities):
        cdf = df[df["name"] == name].sort_values("date").copy()

        en_name = EN_NAMES.get(name, name)
        unit = get_unit(name)
        base_price = round(cdf["price_avg"].median())
        vol_raw = cdf["price_avg"].pct_change().std() if len(cdf) > 5 else 0.05
        vol = round(vol_raw, 4) if np.isfinite(vol_raw) else 0.05

        commodities_js.append({
            "name": name,
            "en": en_name,
            "unit": unit,
            "base": base_price,
            "vol": vol,
        })

        # Historical data
        hist = []
        for _, row in cdf.iterrows():
            dt = row["date"]
            p_min = row["price_min"] if pd.notna(row["price_min"]) else row["price_avg"]
            p_max = row["price_max"] if pd.notna(row["price_max"]) else row["price_avg"]
            p_avg = row["price_avg"] if pd.notna(row["price_avg"]) else (p_min + p_max) / 2

            hist.append({
                "date": dt.strftime("%Y-%m-%d"),
                "year": int(dt.year),
                "month": int(dt.month) - 1,  # JS months are 0-indexed
                "day": int(dt.day),
                "min": round(float(p_min)),
                "max": round(float(p_max)),
                "avg": round(float(p_avg)),
                "isPred": False,
            })

        # Predictions
        pred = []
        # Map commodity name to feature file name for forecast lookup
        safe_name = re.sub(r'[^\w\s]', '', name)[:50].strip().replace(' ', '_')

        if has_forecasts and safe_name in forecasts:
            fc = forecasts[safe_name]
            last_avg = hist[-1]["avg"] if hist else base_price
            # Use last known spread ratio for min/max estimation
            last_spread_ratio = 0.1
            if len(cdf) > 0:
                last_row = cdf.iloc[-1]
                if pd.notna(last_row.get("price_min")) and pd.notna(last_row.get("price_max")) and last_row["price_avg"] > 0:
                    last_spread_ratio = (last_row["price_max"] - last_row["price_min"]) / last_row["price_avg"]

            for _, frow in fc.iterrows():
                dt = frow["date"]
                pp = float(frow["predicted_price"])
                spread = pp * last_spread_ratio
                pred.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "year": int(dt.year),
                    "month": int(dt.month) - 1,
                    "day": int(dt.day),
                    "min": round(pp - spread / 2),
                    "max": round(pp + spread / 2),
                    "avg": round(pp),
                    "isPred": True,
                })
        else:
            # Simple trend-based prediction (fallback when no ML forecasts)
            if len(cdf) >= 30:
                recent = cdf.tail(30)["price_avg"].values
                trend = np.polyfit(range(len(recent)), recent, 1)[0]
                last_price = float(cdf.iloc[-1]["price_avg"])
                last_min = float(cdf.iloc[-1].get("price_min", last_price * 0.95))
                last_max = float(cdf.iloc[-1].get("price_max", last_price * 1.05))
                spread = last_max - last_min if last_max > last_min else last_price * 0.1

                pp = last_price
                for i in range(1, 31):  # 30 days forecast
                    dt = today + timedelta(days=i)
                    # Simple random walk with trend
                    noise = np.random.normal(0, vol * base_price * 0.05)
                    pp = pp + trend + noise
                    pp = max(base_price * 0.3, pp)
                    pred.append({
                        "date": dt.strftime("%Y-%m-%d"),
                        "year": int(dt.year),
                        "month": int(dt.month) - 1,
                        "day": int(dt.day),
                        "min": round(pp - spread / 2),
                        "max": round(pp + spread / 2),
                        "avg": round(pp),
                        "isPred": True,
                    })

        data_js[name] = {"hist": hist, "pred": pred}

    # Generate JavaScript file
    today_str = today.strftime("%Y-%m-%d")
    today_parts = f"new Date({today.year},{today.month-1},{today.day})"

    js_lines = [
        "// Auto-generated by generate_dashboard_data.py",
        f"// Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"// Data from: {df['date'].min().strftime('%Y-%m-%d')} to {today_str}",
        f"// Commodities: {len(commodities_js)}",
        f"// ML Forecasts: {'Yes' if has_forecasts else 'No (trend-based fallback)'}",
        "",
        f"var REAL_DATA_LOADED = true;",
        f"var DATA_LAST_UPDATED = '{today_str}';",
        f"var TODAY = {today_parts};",
        "",
        f"var COMMODITIES = {json.dumps(commodities_js, ensure_ascii=False, indent=2)};",
        "",
        "var DATA = {};",
    ]

    # Write data per commodity (compact JSON to reduce file size)
    for name in sorted(data_js.keys()):
        d = data_js[name]
        # Compact: no indentation for data arrays
        hist_json = json.dumps(d["hist"], ensure_ascii=False, separators=(',', ':'))
        pred_json = json.dumps(d["pred"], ensure_ascii=False, separators=(',', ':'))
        escaped_name = name.replace("'", "\\'")
        js_lines.append(f"DATA['{escaped_name}'] = {{hist:{hist_json},pred:{pred_json}}};")

    js_content = "\n".join(js_lines) + "\n"

    DASHBOARD_DATA_JS.write_text(js_content, encoding="utf-8")
    size_mb = DASHBOARD_DATA_JS.stat().st_size / (1024 * 1024)

    # Update the "Last Updated" text in dashboard.html (only the HTML part, not JS)
    dashboard_path = PROJECT_DIR / "dashboard.html"
    if dashboard_path.exists():
        html = dashboard_path.read_text(encoding="utf-8")
        import re as regex
        # Only match the specific HTML div with Last Updated (not JS code)
        html = regex.sub(
            r'(color:var\(--text3\)">)Last Updated: [^<]+',
            rf'\1Last Updated: {today.strftime("%B %d, %Y")}',
            html
        )
        dashboard_path.write_text(html, encoding="utf-8")

    print(f"\nGenerated: {DASHBOARD_DATA_JS}")
    print(f"File size: {size_mb:.2f} MB")
    print(f"Commodities: {len(commodities_js)}")
    print(f"ML forecasts: {'Yes' if has_forecasts else 'No (using trend fallback)'}")
    date_min = df['date'].min().strftime('%Y-%m-%d')
    print(f"Data range: {date_min} to {today_str}")
    print(f"Updated dashboard.html")
    print("\nDone! Open dashboard.html in a browser to see real data.")


if __name__ == "__main__":
    main()
