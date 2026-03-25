# -*- coding: utf-8 -*-
"""
Next Bazar Scraper v2 — Scrapes from tcb.gov.bd (new portal).

Strategy:
1. Fetch the paginated listing at https://tcb.gov.bd/pages/daily-rmps
2. Extract all xlsx download URLs + Bengali dates from each page
3. Download each xlsx file (hosted on Oracle Cloud)
4. Parse commodity prices from each xlsx
5. Save as daily CSVs + merged CSV

The listing has ~1216 entries across 122 pages (10 per page).
All data is server-rendered HTML — no JS execution needed.

Usage:
    python scraper.py --test          # Test: download 3 sample xlsx files
    python scraper.py                 # Full scrape: all pages
    python scraper.py --merge-only    # Just merge existing daily CSVs

Author: Jahirul (2026)
"""

import os
import io
import sys
import re
import time
import random
import logging
import argparse
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests
import urllib3
from bs4 import BeautifulSoup
import pandas as pd

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):
        return iterable

# Disable SSL warnings (tcb.gov.bd has cert issues)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LISTING_URL = "https://tcb.gov.bd/pages/daily-rmps"
BASE_URL = "https://tcb.gov.bd"

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw_daily"
XLSX_DIR = DATA_DIR / "raw_xlsx"
MERGED_FILE = DATA_DIR / "all_prices_raw.csv"

LOG_FILE = Path(__file__).parent / "scraper.log"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "bn-BD,bn;q=0.9,en;q=0.8",
}

# Bengali digit mapping
BANGLA_DIGITS = {"০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4",
                 "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9"}

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
# Helpers
# ---------------------------------------------------------------------------

def bangla_to_english(text: str) -> str:
    """Convert Bengali digits to English."""
    for bn, en in BANGLA_DIGITS.items():
        text = text.replace(bn, en)
    return text


def parse_bengali_date(text: str) -> Optional[str]:
    """
    Parse Bengali date like '০৯-০৩-২০২৬' to '2026-03-09'.
    Format: DD-MM-YYYY in Bengali digits.
    """
    text = bangla_to_english(text.strip())
    # Try DD-MM-YYYY
    match = re.match(r'(\d{1,2})-(\d{1,2})-(\d{4})', text)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return None


# ---------------------------------------------------------------------------
# Step 1: Scrape listing pages to get xlsx URLs + dates
# ---------------------------------------------------------------------------

def _extract_entries_from_soup(soup) -> list:
    """Extract entries from a parsed listing page."""
    entries = []
    table = soup.find("table", id="noticeTable")
    if not table:
        return entries

    tbody = table.find("tbody")
    if not tbody:
        return entries

    rows = tbody.find_all("tr", class_="table-tr")

    for row in rows:
        # Skip the filter/search row
        if row.find("input"):
            continue

        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        # Extract date (Bengali)
        date_cell = row.find("td", {"data-column": "publish_date"})
        date_text = date_cell.get_text(strip=True) if date_cell else ""
        parsed_date = parse_bengali_date(date_text) if date_text else None

        # Extract xlsx download link
        files_cell = row.find("td", {"data-column": "files"})
        xlsx_url = None
        if files_cell:
            link = files_cell.find("a", href=True)
            if link:
                xlsx_url = link["href"]

        # Extract detail page link
        detail_link = None
        action_cell = cells[-1] if cells else None
        if action_cell:
            a = action_cell.find("a", href=True)
            if a and a["href"].startswith("/pages/"):
                detail_link = BASE_URL + a["href"]

        if parsed_date and xlsx_url:
            entries.append({
                "date": parsed_date,
                "xlsx_url": xlsx_url,
                "detail_url": detail_link,
                "date_bengali": date_text,
            })

    return entries


def get_all_entries(session: requests.Session, stop_at_date: str = None) -> list[dict]:
    """
    Fetch entries from the TCB daily-rmps listing.
    Handles pagination via ?page=N URL parameter.

    Args:
        stop_at_date: If provided (YYYY-MM-DD), stop fetching pages once all
                      entries on a page are at or before this date. This enables
                      incremental scraping — only fetch listing pages until we
                      reach dates we already have. The listing is newest-first,
                      so once we see old dates, we can stop.
    """
    all_entries = []

    # Fetch first page to get total count
    logger.info("Fetching listing page 1...")
    try:
        resp = session.get(LISTING_URL, headers=HEADERS, timeout=60, verify=False)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch listing page: {e}")
        return all_entries

    soup = BeautifulSoup(resp.text, "html.parser")
    page1_entries = _extract_entries_from_soup(soup)
    all_entries.extend(page1_entries)
    logger.info(f"Page 1: {len(page1_entries)} entries")

    # Early stop check for first page
    if stop_at_date and page1_entries:
        new_on_page = [e for e in page1_entries if e["date"] > stop_at_date]
        if not new_on_page:
            logger.info(f"All entries on page 1 are at or before {stop_at_date}. No new data on site.")
            return []

    # Get total from pagination meta: "দেখছেন ১ থেকে ১০ পর্যন্ত, মোট ১২১৬ এন্ট্রি"
    pagination_text = bangla_to_english(resp.text)
    total_match = re.search(r'মোট\s+(\d+)\s+এন্ট্রি', pagination_text)
    total_entries = int(total_match.group(1)) if total_match else len(page1_entries)
    logger.info(f"Total entries on site: {total_entries}")

    # Get total pages from pagination: data-page="122"
    max_page = 1
    pagination = soup.find("ul", class_="pagination")
    if pagination:
        page_links = pagination.find_all("a", {"data-page": True})
        for pl in page_links:
            try:
                p = int(pl["data-page"])
                if p > max_page:
                    max_page = p
            except (ValueError, KeyError):
                pass
    logger.info(f"Max page number: {max_page}")

    # Fetch remaining pages
    stop_early = False
    if max_page > 1:
        for page in tqdm(range(2, max_page + 1), desc="Fetching listing pages"):
            if stop_early:
                break

            try:
                # Try different pagination URL patterns
                for url_pattern in [
                    f"{LISTING_URL}?page={page}",
                    f"{LISTING_URL}?p={page}",
                ]:
                    resp = session.get(url_pattern, headers=HEADERS, timeout=30, verify=False)
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    entries = _extract_entries_from_soup(soup)

                    if entries:
                        # Check if these are actually different from previous pages
                        new_dates = {e["date"] for e in entries}
                        existing_dates = {e["date"] for e in all_entries}
                        truly_new = new_dates - existing_dates

                        if truly_new:
                            all_entries.extend(entries)
                            logger.info(f"Page {page}: +{len(entries)} entries ({len(truly_new)} new)")

                            # EARLY STOP: if all entries on this page are at/before our latest date,
                            # we've reached data we already have — no need to fetch more pages
                            if stop_at_date:
                                new_entries_on_page = [e for e in entries if e["date"] > stop_at_date]
                                if not new_entries_on_page:
                                    logger.info(f"Reached existing data at page {page}. Stopping early.")
                                    stop_early = True
                            break
                        else:
                            # Same data as before — pagination params might not work
                            logger.debug(f"Page {page}: duplicate data with {url_pattern}")
                            continue

                time.sleep(0.3 + random.random() * 0.3)

            except Exception as e:
                logger.warning(f"Error fetching page {page}: {e}")

    # If pagination didn't work (all pages return same data), try detail page approach
    if not stop_early and not stop_at_date and len(all_entries) < total_entries * 0.5:
        logger.warning(
            f"Only got {len(all_entries)}/{total_entries} entries. "
            "Pagination may not work via URL params. "
            "The DatatableBrowseWidget likely uses client-side JS pagination. "
            "Consider using Selenium or increasing pageSize."
        )
        logger.info(
            "TIP: Open the page in a browser, set page size to 100, "
            "and use browser dev tools to extract all xlsx URLs. "
            "Or check if the site has an API endpoint."
        )

    # Deduplicate by date
    seen = set()
    unique = []
    for e in all_entries:
        if e["date"] not in seen:
            seen.add(e["date"])
            unique.append(e)

    # If incremental mode, filter to only entries newer than stop_at_date
    if stop_at_date:
        unique = [e for e in unique if e["date"] > stop_at_date]
        logger.info(f"New entries (after {stop_at_date}): {len(unique)}")
    else:
        logger.info(f"Total unique entries: {len(unique)}")

    return unique


# ---------------------------------------------------------------------------
# Step 2: Download and parse xlsx files
# ---------------------------------------------------------------------------

def download_xlsx(url: str, session: requests.Session, save_path: Path) -> bool:
    """Download an xlsx file from Oracle Cloud storage."""
    for attempt in range(3):
        try:
            resp = session.get(url, headers=HEADERS, timeout=60, verify=False)
            resp.raise_for_status()

            if len(resp.content) < 100:
                logger.warning(f"Suspiciously small file: {len(resp.content)} bytes")
                return False

            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(resp.content)
            return True

        except Exception as e:
            logger.warning(f"Download attempt {attempt+1}/3 failed: {e}")
            time.sleep(2 ** attempt)

    return False


def parse_xlsx(file_path: Path, date_str: str) -> Optional[pd.DataFrame]:
    """
    Parse a TCB daily price xlsx file.

    The xlsx structure (as of 2026):
      Rows 0-7:  Metadata (org name, title, memo number, date)
      Row 8:     Column headers (পণ্যের নাম, মাপের একক, অদ্যকার মূল্য, ...)
      Row 9:     Date sub-headers (actual dates for each period)
      Row 10:    First category header (চাল) + min/max sub-headers (সর্বনিম্ন/সর্ব্বোচ্চ)
      Row 11+:   Data rows, with category headers interspersed

    Category headers are identified by having NaN in the unit column (col 1).
    We assign fixed column names:
      name, unit, today_min, today_max, week_min, week_max,
      month_min, month_max, month_change, year_min, year_max, year_change
    """
    COLUMN_NAMES = [
        "name", "unit", "today_min", "today_max",
        "week_min", "week_max", "month_min", "month_max",
        "month_change", "year_min", "year_max", "year_change",
    ]

    try:
        xl = pd.ExcelFile(file_path, engine="openpyxl")

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name, header=None)

            if df.empty or len(df) < 5:
                continue

            # Find the header row containing "পণ্যের নাম" or "অদ্যকার"
            header_row = None
            for i in range(min(20, len(df))):
                row_text = " ".join(str(v) for v in df.iloc[i].values if pd.notna(v))
                if "পণ্যের নাম" in row_text or ("পণ্য" in row_text and "একক" in row_text):
                    header_row = i
                    break

            if header_row is None:
                # Fallback: look for row with "সর্বনিম্ন" (min) which is 2 rows after header
                for i in range(min(20, len(df))):
                    row_text = " ".join(str(v) for v in df.iloc[i].values if pd.notna(v))
                    if "সর্বনিম্ন" in row_text:
                        header_row = max(0, i - 2)
                        break

            if header_row is None:
                continue

            # Data starts after header row + 2 sub-header rows
            # (row header_row+1 = date sub-headers, header_row+2 = category + min/max sub-headers)
            data_start = header_row + 1  # We start from header_row+1 and filter below

            # Find the END of the main table — a second section with price changes
            # starts after a row containing "অন্যান্য পণ্যের" or "যে সকল পণ্যের"
            data_end = len(df)
            for i in range(data_start, len(df)):
                row_text = " ".join(str(v) for v in df.iloc[i].values if pd.notna(v))
                if any(kw in row_text for kw in [
                    "অন্যান্য পণ্যের", "যে সকল পণ্যের", "অপরিবর্তীত",
                    "সদয় অবগতি", "পরিচালক", "মজুমদার",
                ]):
                    data_end = i
                    break

            # Take rows from the main table only
            data_df = df.iloc[data_start:data_end].reset_index(drop=True)

            if len(data_df.columns) < 12:
                # Pad if fewer columns
                while len(data_df.columns) < 12:
                    data_df[len(data_df.columns)] = None

            # Assign fixed column names (take first 12 columns only)
            data_df = data_df.iloc[:, :12]
            data_df.columns = COLUMN_NAMES

            # Filter out non-data rows:
            # 1. Drop rows where name is NaN or empty
            data_df = data_df[data_df["name"].notna()]
            data_df["name"] = data_df["name"].astype(str).str.strip()
            data_df = data_df[data_df["name"].str.len() > 0]

            # 2. Drop rows where unit is NaN/empty (these are category headers or sub-headers)
            data_df = data_df[data_df["unit"].notna()]
            data_df["unit"] = data_df["unit"].astype(str).str.strip()
            data_df = data_df[data_df["unit"].str.len() > 0]

            # 3. Drop rows that are sub-headers (contain সর্বনিম্ন, dates, হ্রাস/বৃদ্ধি)
            filter_keywords = ["সর্বনিম্ন", "সর্ব্বোচ্চ", "হ্রাস", "বৃদ্ধি", "মাপের একক"]
            mask = data_df["unit"].apply(
                lambda x: not any(kw in str(x) for kw in filter_keywords)
            )
            data_df = data_df[mask]

            # 4. Drop rows where today_min is not a valid number
            def is_numeric_like(val):
                if pd.isna(val):
                    return False
                s = bangla_to_english(str(val).strip())
                try:
                    float(s)
                    return True
                except (ValueError, TypeError):
                    return False

            data_df = data_df[data_df["today_min"].apply(is_numeric_like)]

            # Convert Bengali numerals in price columns
            price_cols = [c for c in COLUMN_NAMES if c not in ("name", "unit")]
            for col in price_cols:
                data_df[col] = data_df[col].apply(
                    lambda x: bangla_to_english(str(x).strip()) if pd.notna(x) else x
                )
                data_df[col] = pd.to_numeric(data_df[col], errors="coerce")

            # Add date
            data_df["date"] = date_str

            data_df = data_df.reset_index(drop=True)

            if len(data_df) >= 3:
                return data_df

        return None

    except Exception as e:
        logger.error(f"Error parsing {file_path}: {e}")
        return None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def scrape_all(skip_existing: bool = True, stop_at_date: str = None):
    """
    Full scrape: listing -> download xlsx -> parse -> merge.

    Args:
        skip_existing: Skip dates that already have CSV files (default True)
        stop_at_date: If provided (YYYY-MM-DD), only fetch listing pages with
                      entries newer than this date, and only download those new entries.
                      This makes incremental updates much faster.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    XLSX_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()

    entries = get_all_entries(session, stop_at_date=stop_at_date)
    if not entries:
        if stop_at_date:
            logger.info("No new entries found on TCB website.")
        else:
            logger.error("No entries found!")
        return

    logger.info(f"\nDownloading {len(entries)} xlsx files...")

    success = 0
    failed = 0

    for entry in tqdm(entries, desc="Downloading & parsing"):
        date_str = entry["date"]
        xlsx_url = entry["xlsx_url"]
        xlsx_path = XLSX_DIR / f"{date_str}.xlsx"
        csv_path = RAW_DIR / f"{date_str}.csv"

        if skip_existing and csv_path.exists():
            success += 1
            continue

        if not xlsx_path.exists() or not skip_existing:
            ok = download_xlsx(xlsx_url, session, xlsx_path)
            if not ok:
                failed += 1
                continue
            time.sleep(0.3 + random.random() * 0.3)

        df = parse_xlsx(xlsx_path, date_str)
        if df is not None and len(df) > 0:
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            success += 1
        else:
            logger.warning(f"Could not parse: {xlsx_path.name}")
            failed += 1

    logger.info(f"\nComplete: {success} success, {failed} failed")


def merge_daily_csvs() -> pd.DataFrame:
    """Merge all daily CSVs into one file."""
    csv_files = sorted(RAW_DIR.glob("*.csv"))
    logger.info(f"Merging {len(csv_files)} daily CSV files...")

    dfs = []
    for f in tqdm(csv_files, desc="Merging"):
        try:
            df = pd.read_csv(f, encoding="utf-8-sig")
            if len(df) > 0:
                dfs.append(df)
        except Exception as e:
            logger.warning(f"Error reading {f}: {e}")

    if not dfs:
        logger.error("No data files found!")
        return pd.DataFrame()

    merged = pd.concat(dfs, ignore_index=True)
    merged.to_csv(MERGED_FILE, index=False, encoding="utf-8-sig")
    logger.info(f"Merged: {len(merged)} rows, {merged['date'].nunique()} dates")
    return merged


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Next Bazar Scraper v2")
    parser.add_argument("--test", action="store_true",
                        help="Test: download and parse 3 sample files")
    parser.add_argument("--no-skip", action="store_true",
                        help="Re-download even if files exist")
    parser.add_argument("--merge-only", action="store_true",
                        help="Only merge existing daily CSVs")
    parser.add_argument("--stop-at-date", type=str, default=None,
                        help="Only fetch entries newer than this date (YYYY-MM-DD). "
                             "Enables fast incremental scraping.")
    args = parser.parse_args()

    if args.merge_only:
        merge_daily_csvs()
        return

    if args.test:
        logger.info("TEST MODE: Fetching listing and downloading 3 samples...")
        session = requests.Session()

        entries = get_all_entries(session)
        if not entries:
            logger.error("No entries found!")
            return

        logger.info(f"Found {len(entries)} entries. Testing first 3...")
        XLSX_DIR.mkdir(parents=True, exist_ok=True)
        RAW_DIR.mkdir(parents=True, exist_ok=True)

        for entry in entries[:3]:
            date_str = entry["date"]
            xlsx_url = entry["xlsx_url"]
            xlsx_path = XLSX_DIR / f"{date_str}.xlsx"

            logger.info(f"\n--- {date_str} ---")
            logger.info(f"URL: {xlsx_url}")

            ok = download_xlsx(xlsx_url, session, xlsx_path)
            if ok:
                logger.info(f"Downloaded: {xlsx_path} ({xlsx_path.stat().st_size} bytes)")

                df = parse_xlsx(xlsx_path, date_str)
                if df is not None:
                    logger.info(f"Parsed: {len(df)} rows")
                    logger.info(f"Columns: {list(df.columns)}")
                    print(df.head(5).to_string())

                    csv_path = RAW_DIR / f"{date_str}.csv"
                    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
                else:
                    logger.warning("Parse failed!")
            else:
                logger.error("Download failed!")

            time.sleep(1)
        return

    # Full scrape (with optional incremental mode)
    scrape_all(skip_existing=not args.no_skip, stop_at_date=args.stop_at_date)
    merge_daily_csvs()


if __name__ == "__main__":
    main()
