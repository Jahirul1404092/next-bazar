# -*- coding: utf-8 -*-
"""
Site Diagnostic v2 — Fixes SSL issues and probes DAM POST API.

Usage:
    python diagnose_v2.py

Output: diagnostic_report_v2.txt
"""

import os
import sys
import re
import json
import urllib3
from pathlib import Path
from datetime import date

import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DIAG_DIR = Path(__file__).parent / "data" / "diagnostics"
DIAG_DIR.mkdir(parents=True, exist_ok=True)

REPORT = []

def log(msg):
    print(msg)
    REPORT.append(str(msg))


def save_html(html: str, name: str):
    path = DIAG_DIR / f"{name}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"  Saved: {path.name}")


# =========================================================================
# 1. TCB gov.bd with SSL disabled
# =========================================================================
def diagnose_tcb():
    log("\n" + "=" * 70)
    log("1. tcb.gov.bd (SSL verify=False)")
    log("=" * 70)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "bn-BD,bn;q=0.9,en;q=0.8",
    })

    urls = [
        "https://tcb.gov.bd/pages/daily-rmps",
        "https://tcb.gov.bd/site/view/daily_rmp",
    ]

    for url in urls:
        log(f"\n--- {url}")
        try:
            resp = session.get(url, timeout=30, verify=False, allow_redirects=True)
            log(f"  Status: {resp.status_code}, Final: {resp.url}")
            log(f"  Length: {len(resp.text)} chars")
            save_html(resp.text, f"tcb_v2_{url.split('/')[-1][:30]}")

            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.get_text(strip=True)[:80] if soup.title else "No title"
            log(f"  Title: {title}")

            # Tables
            tables = soup.find_all("table")
            log(f"  Tables: {len(tables)}")
            for i, table in enumerate(tables[:3]):
                rows = table.find_all("tr")
                log(f"    Table {i}: {len(rows)} rows, id={table.get('id','')}, class={table.get('class','')}")
                for j, row in enumerate(rows[:4]):
                    cells = [c.get_text(strip=True)[:50] for c in row.find_all(["td", "th"])]
                    log(f"      Row {j}: {cells}")

            # Links to xlsx/pdf/download
            links = soup.find_all("a", href=True)
            dl_links = [l["href"] for l in links
                        if any(ext in l["href"].lower() for ext in [".xlsx", ".csv", ".pdf", "download"])]
            if dl_links:
                log(f"  Download links ({len(dl_links)}):")
                for dl in dl_links[:15]:
                    log(f"    {dl}")

            # All links containing 'daily' or 'rmp' or 'price'
            relevant = [l["href"] for l in links
                        if any(kw in l["href"].lower() for kw in ["daily", "rmp", "price", "bazar"])]
            if relevant:
                log(f"  Relevant links ({len(relevant)}):")
                for r in relevant[:15]:
                    log(f"    {r}")

            # JS/API endpoints in page source
            api_hits = re.findall(r'(?:fetch|axios|ajax|url|href|src)\s*[:(=]\s*["\']([^"\']+)["\']', resp.text)
            api_hits = [a for a in api_hits if any(kw in a.lower() for kw in ["api", "json", "data", "price", "rmp", "daily"])]
            if api_hits:
                log(f"  JS API endpoints:")
                for a in set(api_hits):
                    log(f"    {a}")

        except Exception as e:
            log(f"  ERROR: {e}")

    # Try portal with SSL disabled
    log(f"\n--- tcb.portal.gov.bd (SSL verify=False)")
    try:
        resp = session.get(
            "https://tcb.portal.gov.bd/sites/default/files/files/tcb.portal.gov.bd/daily_rmp/",
            timeout=30, verify=False
        )
        log(f"  Status: {resp.status_code}")
        save_html(resp.text, "tcb_portal_v2")
        soup = BeautifulSoup(resp.text, "html.parser")
        links = [a["href"] for a in soup.find_all("a", href=True)]
        log(f"  Links: {len(links)}")
        for l in links[:20]:
            log(f"    {l}")
    except Exception as e:
        log(f"  ERROR: {e}")


# =========================================================================
# 2. DAM — Probe the POST API
# =========================================================================
def diagnose_dam():
    log("\n" + "=" * 70)
    log("2. market.dam.gov.bd — POST API probing")
    log("=" * 70)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    })

    # First, get the page to find CSRF tokens, hidden fields, and JS endpoints
    log("\n--- GET initial page (English)")
    try:
        resp = session.get("https://market.dam.gov.bd/market_daily_price_report?L=E", timeout=30)
        log(f"  Status: {resp.status_code}")
        save_html(resp.text, "dam_v2_initial")

        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for CSRF tokens
        csrf = soup.find("meta", {"name": "csrf-token"})
        if csrf:
            log(f"  CSRF token: {csrf.get('content', '')[:40]}")

        csrf_input = soup.find("input", {"name": "_token"})
        if csrf_input:
            log(f"  _token input: {csrf_input.get('value', '')[:40]}")

        # Look for ALL script tags and find AJAX/fetch calls
        scripts = soup.find_all("script")
        log(f"  Script tags: {len(scripts)}")
        for i, script in enumerate(scripts):
            src = script.get("src", "")
            text = script.string or ""
            if src:
                log(f"    Script {i}: src={src[:80]}")
            if any(kw in text.lower() for kw in ["ajax", "fetch", "api", "price", "market", "url", "route"]):
                # Extract URLs and API patterns from inline scripts
                urls_found = re.findall(r'["\']([^"\']*(?:api|market|price|daily|report|division|district|commodity)[^"\']*)["\']', text, re.I)
                if urls_found:
                    log(f"    Script {i} API URLs:")
                    for u in set(urls_found):
                        log(f"      {u}")

                # Also look for route patterns
                routes = re.findall(r'(?:url|route|endpoint|action)\s*[:=]\s*["\']([^"\']+)["\']', text, re.I)
                if routes:
                    log(f"    Script {i} routes:")
                    for r in set(routes):
                        log(f"      {r}")

                # Save interesting scripts
                if len(text) > 100:
                    script_path = DIAG_DIR / f"dam_script_{i}.js"
                    with open(script_path, "w", encoding="utf-8") as f:
                        f.write(text)
                    log(f"    Saved script to dam_script_{i}.js ({len(text)} chars)")

        # Extract full inline JS for analysis
        all_js = "\n".join([s.string for s in scripts if s.string and len(s.string) > 50])
        if all_js:
            js_path = DIAG_DIR / "dam_all_js.js"
            with open(js_path, "w", encoding="utf-8") as f:
                f.write(all_js)
            log(f"  All inline JS saved: dam_all_js.js ({len(all_js)} chars)")

    except Exception as e:
        log(f"  ERROR: {e}")

    # Try common API endpoints
    log("\n--- Probing common API endpoints")
    api_attempts = [
        ("GET", "https://market.dam.gov.bd/api/market_daily_price_report", {}),
        ("GET", "https://market.dam.gov.bd/api/division", {}),
        ("GET", "https://market.dam.gov.bd/api/districts", {}),
        ("GET", "https://market.dam.gov.bd/api/commodities", {}),
        ("GET", "https://market.dam.gov.bd/api/commodity-categories", {}),
        ("GET", "https://market.dam.gov.bd/divisions", {}),
        ("GET", "https://market.dam.gov.bd/get-divisions", {}),
        ("GET", "https://market.dam.gov.bd/get-districts", {}),
        ("GET", "https://market.dam.gov.bd/get-markets", {}),
        ("POST", "https://market.dam.gov.bd/market_daily_price_report", {
            "Division_id[]": "",
            "district_id[]": "",
            "sub_district_id[]": "",
            "market_id[]": "",
            "PriceType_id[]": "4",  # Retail
        }),
    ]

    for method, url, data in api_attempts:
        try:
            if method == "GET":
                r = session.get(url, timeout=15)
            else:
                r = session.post(url, data=data, timeout=15)

            ct = r.headers.get("Content-Type", "")
            log(f"  {method} {url.split('dam.gov.bd')[-1]}")
            log(f"    Status: {r.status_code}, Type: {ct[:40]}, Length: {len(r.text)}")

            # If JSON, show structure
            if "json" in ct.lower() or r.text.strip().startswith(("{", "[")):
                try:
                    j = r.json()
                    if isinstance(j, dict):
                        log(f"    JSON keys: {list(j.keys())[:10]}")
                        # Show first few values
                        for k in list(j.keys())[:3]:
                            val = j[k]
                            if isinstance(val, list):
                                log(f"    {k}: list[{len(val)}] first={val[0] if val else 'empty'}")
                            elif isinstance(val, dict):
                                log(f"    {k}: dict keys={list(val.keys())[:5]}")
                            else:
                                log(f"    {k}: {str(val)[:60]}")
                    elif isinstance(j, list):
                        log(f"    JSON array: {len(j)} items, first={j[0] if j else 'empty'}")
                except:
                    log(f"    (not valid JSON)")

            # If HTML with table, show it
            if "html" in ct.lower() and "<table" in r.text.lower():
                s2 = BeautifulSoup(r.text, "html.parser")
                tables = s2.find_all("table")
                log(f"    Tables in response: {len(tables)}")
                for ti, t in enumerate(tables[:2]):
                    rows = t.find_all("tr")
                    log(f"      Table {ti}: {len(rows)} rows")
                    for ri, row in enumerate(rows[:5]):
                        cells = [c.get_text(strip=True)[:40] for c in row.find_all(["td", "th"])]
                        log(f"        Row {ri}: {cells}")
                save_html(r.text, f"dam_post_response")

        except Exception as e:
            log(f"  {method} {url.split('dam.gov.bd')[-1]}: ERROR {e}")


# =========================================================================
# 3. Alternative: bddata.org (structured CSV/API)
# =========================================================================
def diagnose_bddata():
    log("\n" + "=" * 70)
    log("3. bddata.org — Bangladesh Data Portal")
    log("=" * 70)

    try:
        resp = requests.get(
            "https://www.bddata.org/db/Prices_of_selected_consumer_goods",
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        log(f"  Status: {resp.status_code}")
        save_html(resp.text, "bddata_prices")

        soup = BeautifulSoup(resp.text, "html.parser")
        tables = soup.find_all("table")
        log(f"  Tables: {len(tables)}")
        for i, t in enumerate(tables[:2]):
            rows = t.find_all("tr")
            log(f"    Table {i}: {len(rows)} rows")
            for j, row in enumerate(rows[:5]):
                cells = [c.get_text(strip=True)[:50] for c in row.find_all(["td", "th"])]
                log(f"      Row {j}: {cells}")

        # Look for download/API links
        links = [a["href"] for a in soup.find_all("a", href=True)
                 if any(kw in a["href"].lower() for kw in ["csv", "xlsx", "download", "api", "json"])]
        if links:
            log(f"  Download/API links:")
            for l in links[:10]:
                log(f"    {l}")

    except Exception as e:
        log(f"  ERROR: {e}")


# =========================================================================
# Main
# =========================================================================
def main():
    log("Next Bazar — Site Diagnostic v2")
    log(f"Date: {date.today()}")

    diagnose_tcb()
    diagnose_dam()
    diagnose_bddata()

    log("\n" + "=" * 70)
    log("DONE — Please share diagnostic_report_v2.txt with Claude")
    log("=" * 70)

    report_path = Path(__file__).parent / "diagnostic_report_v2.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(REPORT))
    print(f"\nSaved: {report_path}")

    # Also save all cookies for reference
    log(f"\nAlso check the HTML files saved in: {DIAG_DIR}")


if __name__ == "__main__":
    main()
