# -*- coding: utf-8 -*-
"""
Site Diagnostic Script — Run this on YOUR machine to inspect the current
TCB and DAM website structures so we can build the right scraper.

This will:
1. Fetch pages from both data sources
2. Save raw HTML for inspection
3. Attempt to extract price data using multiple strategies
4. Print a diagnostic report

Usage:
    python diagnose_sites.py

Output: diagnostic_report.txt + raw HTML files in data/diagnostics/
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup
import pandas as pd

DIAG_DIR = Path(__file__).parent / "data" / "diagnostics"
DIAG_DIR.mkdir(parents=True, exist_ok=True)

REPORT = []

def log(msg):
    print(msg)
    REPORT.append(msg)


def save_html(html: str, name: str):
    path = DIAG_DIR / f"{name}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"  Saved HTML: {path}")


# =========================================================================
# Source 1: tcb.gov.bd — New TCB portal
# =========================================================================

def diagnose_tcb_portal():
    log("\n" + "=" * 70)
    log("SOURCE 1: tcb.gov.bd (TCB Government Portal)")
    log("=" * 70)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "bn-BD,bn;q=0.9,en;q=0.8",
    })

    # --- 1a: Main daily RMP listing page ---
    urls_to_try = [
        "https://tcb.gov.bd/pages/daily-rmps",
        "https://tcb.gov.bd/site/view/daily_rmp",
        "https://tcb.gov.bd/site/view/daily_rmp/Today's-retail-market-price-in-Dhaka-city",
    ]

    for url in urls_to_try:
        log(f"\n--- Trying: {url}")
        try:
            resp = session.get(url, timeout=30, allow_redirects=True)
            log(f"  Status: {resp.status_code}")
            log(f"  Final URL: {resp.url}")
            log(f"  Content-Type: {resp.headers.get('Content-Type', 'unknown')}")
            log(f"  Content length: {len(resp.text)} chars")

            save_html(resp.text, f"tcb_{url.split('/')[-1][:30]}")

            soup = BeautifulSoup(resp.text, "html.parser")

            # Look for tables
            tables = soup.find_all("table")
            log(f"  Tables found: {len(tables)}")
            for i, table in enumerate(tables):
                rows = table.find_all("tr")
                log(f"    Table {i}: {len(rows)} rows")
                if rows:
                    # Print first 3 rows
                    for j, row in enumerate(rows[:3]):
                        cells = [c.get_text(strip=True)[:40] for c in row.find_all(["td", "th"])]
                        log(f"      Row {j}: {cells}")

            # Look for download links (xlsx, pdf, csv)
            links = soup.find_all("a", href=True)
            download_links = [
                l["href"] for l in links
                if any(ext in l["href"].lower() for ext in [".xlsx", ".csv", ".pdf", "download", "daily_rmp"])
            ]
            log(f"  Download links found: {len(download_links)}")
            for dl in download_links[:10]:
                log(f"    {dl}")

            # Look for date pickers or form elements
            forms = soup.find_all("form")
            log(f"  Forms found: {len(forms)}")
            for form in forms:
                log(f"    Action: {form.get('action', 'none')}")
                inputs = form.find_all("input")
                selects = form.find_all("select")
                log(f"    Inputs: {len(inputs)}, Selects: {len(selects)}")
                for inp in inputs:
                    log(f"      Input: name={inp.get('name')}, type={inp.get('type')}, value={inp.get('value','')[:30]}")
                for sel in selects:
                    options = [o.get_text(strip=True)[:30] for o in sel.find_all("option")[:5]]
                    log(f"      Select: name={sel.get('name')}, options={options}")

            # Look for JavaScript API calls
            scripts = soup.find_all("script")
            api_patterns = re.findall(r'(https?://[^\s"\'>]+(?:api|ajax|json|data|rmp|price)[^\s"\'>]*)', resp.text)
            if api_patterns:
                log(f"  Possible API endpoints found:")
                for ap in set(api_patterns):
                    log(f"    {ap}")

            # Look for pagination
            pagination = soup.find_all(["nav", "ul"], class_=lambda c: c and "paginat" in str(c).lower())
            if pagination:
                log(f"  Pagination elements found: {len(pagination)}")

        except Exception as e:
            log(f"  ERROR: {e}")

    # --- 1b: Try the old-style URL pattern (might redirect) ---
    log(f"\n--- Trying old tcbbazardor.com pattern:")
    for test_date in ["2026/03/01", "2025/01/15", "2024/06/15"]:
        url = f"http://tcbbazardor.com/home/index/{test_date}"
        try:
            resp = session.get(url, timeout=15, allow_redirects=True)
            log(f"  {url}")
            log(f"    Status: {resp.status_code}, Final URL: {resp.url}")
            log(f"    Title: {BeautifulSoup(resp.text, 'html.parser').title.get_text()[:60] if BeautifulSoup(resp.text, 'html.parser').title else 'No title'}")
        except Exception as e:
            log(f"  {url}: ERROR {e}")

    # --- 1c: Try portal URL for Excel downloads ---
    log(f"\n--- Trying TCB portal Excel download pattern:")
    portal_url = "https://tcb.portal.gov.bd/sites/default/files/files/tcb.portal.gov.bd/daily_rmp/"
    try:
        resp = session.get(portal_url, timeout=15)
        log(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            save_html(resp.text, "tcb_portal_daily_rmp")
            soup = BeautifulSoup(resp.text, "html.parser")
            links = [a["href"] for a in soup.find_all("a", href=True)]
            log(f"  Links found: {len(links)}")
            for l in links[:20]:
                log(f"    {l}")
    except Exception as e:
        log(f"  ERROR: {e}")


# =========================================================================
# Source 2: DAM (Department of Agricultural Marketing)
# =========================================================================

def diagnose_dam():
    log("\n" + "=" * 70)
    log("SOURCE 2: market.dam.gov.bd (Dept of Agricultural Marketing)")
    log("=" * 70)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    })

    urls = [
        "https://market.dam.gov.bd/market_daily_price_report?L=E",
        "https://market.dam.gov.bd/market_daily_price_report?L=B",
    ]

    for url in urls:
        log(f"\n--- Trying: {url}")
        try:
            resp = session.get(url, timeout=30)
            log(f"  Status: {resp.status_code}")
            log(f"  Content length: {len(resp.text)} chars")

            name = "dam_english" if "L=E" in url else "dam_bangla"
            save_html(resp.text, name)

            soup = BeautifulSoup(resp.text, "html.parser")

            # Forms
            forms = soup.find_all("form")
            log(f"  Forms found: {len(forms)}")
            for form in forms:
                log(f"    Action: {form.get('action', 'none')}, Method: {form.get('method', 'GET')}")
                for sel in form.find_all("select"):
                    name_attr = sel.get("name", sel.get("id", "unknown"))
                    options = [(o.get("value", ""), o.get_text(strip=True)[:30]) for o in sel.find_all("option")[:8]]
                    log(f"    Select '{name_attr}': {options}")

            # Tables
            tables = soup.find_all("table")
            log(f"  Tables found: {len(tables)}")
            for i, table in enumerate(tables):
                rows = table.find_all("tr")
                log(f"    Table {i}: {len(rows)} rows")
                for j, row in enumerate(rows[:5]):
                    cells = [c.get_text(strip=True)[:40] for c in row.find_all(["td", "th"])]
                    log(f"      Row {j}: {cells}")

        except Exception as e:
            log(f"  ERROR: {e}")


# =========================================================================
# Source 3: The Daily Star (alternative structured data)
# =========================================================================

def diagnose_dailystar():
    log("\n" + "=" * 70)
    log("SOURCE 3: thedailystar.net/health/food/price-essentials")
    log("=" * 70)

    try:
        resp = requests.get(
            "https://www.thedailystar.net/health/food/price-essentials",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        log(f"  Status: {resp.status_code}")
        save_html(resp.text, "dailystar_prices")

        soup = BeautifulSoup(resp.text, "html.parser")
        tables = soup.find_all("table")
        log(f"  Tables found: {len(tables)}")
        for i, table in enumerate(tables[:3]):
            rows = table.find_all("tr")
            log(f"    Table {i}: {len(rows)} rows")
            for j, row in enumerate(rows[:5]):
                cells = [c.get_text(strip=True)[:40] for c in row.find_all(["td", "th"])]
                log(f"      Row {j}: {cells}")

    except Exception as e:
        log(f"  ERROR: {e}")


# =========================================================================
# Main
# =========================================================================

def main():
    log("Next Bazar — Site Diagnostic Report")
    log(f"Date: {date.today()}")
    log(f"Python: {sys.version}")

    diagnose_tcb_portal()
    diagnose_dam()
    diagnose_dailystar()

    log("\n" + "=" * 70)
    log("DIAGNOSTIC COMPLETE")
    log("=" * 70)
    log(f"\nAll HTML files saved in: {DIAG_DIR}")
    log("Please share the content of diagnostic_report.txt with Claude.")

    # Save report
    report_path = Path(__file__).parent / "diagnostic_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(REPORT))
    print(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    main()
