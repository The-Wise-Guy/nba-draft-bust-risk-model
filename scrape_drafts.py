"""
scrape_drafts.py
----------------
Step 1 of the data pull: every pick of the 2005-2021 NBA drafts -> `players` table.

  python3 scrape_drafts.py               # download (cached) + load into the database
  python3 scrape_drafts.py --from-cache  # no network, parse files already in data/raw/
  python3 scrape_drafts.py --years 2015 2016

Source: https://www.basketball-reference.com/draft/NBA_<year>.html

Politeness (Basketball-Reference rate-limits and will block scrapers):
  * waits REQUEST_DELAY_SECONDS between requests (their limit is 20/minute)
  * saves each page to data/raw/draft_<year>.html and never downloads it twice
  * stops immediately on HTTP 429/403 instead of hammering the site
    (if that happens, wait an hour and re-run; cached years are skipped)

Players with no player link on the draft page never played an NBA game. They
are stored with bbref_id = NULL and outcomes_checked = 1, so the labeling step
correctly treats them as busts.
"""

import argparse
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Comment

from build_db import DB_PATH, build_database, tier_for_pick

RAW_DIR = Path(__file__).parent / "data" / "raw"
URL = "https://www.basketball-reference.com/draft/NBA_{year}.html"
FIRST_YEAR, LAST_YEAR = 2005, 2021
REQUEST_DELAY_SECONDS = 4
HEADERS = {"User-Agent": "Mozilla/5.0 (personal portfolio research project; low-volume, cached)"}


def download_year(year: int) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"draft_{year}.html"
    if path.exists():
        return path
    resp = requests.get(URL.format(year=year), headers=HEADERS, timeout=30)
    if resp.status_code in (403, 429):
        sys.exit(f"Blocked/rate-limited (HTTP {resp.status_code}) on {year}. "
                 "Wait about an hour and re-run; already-cached years are skipped.")
    resp.raise_for_status()
    path.write_text(resp.text, encoding="utf-8")
    print(f"  downloaded {year}")
    time.sleep(REQUEST_DELAY_SECONDS)
    return path


def _find_draft_table(soup: BeautifulSoup):
    table = soup.find("table", id="stats")
    if table is not None:
        return table
    # Fallback: Basketball-Reference sometimes ships tables inside HTML comments.
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        if 'id="stats"' in c:
            inner = BeautifulSoup(c, "html.parser").find("table", id="stats")
            if inner is not None:
                return inner
    return None


def parse_draft_page(html: str, year: int) -> list[dict]:
    table = _find_draft_table(BeautifulSoup(html, "html.parser"))
    if table is None:
        raise ValueError(f"No draft table found for {year}")

    picks = []
    for row in table.select("tbody tr"):
        if "thead" in (row.get("class") or []):
            continue  # repeated header / round-divider rows
        pick_cell = row.find("td", {"data-stat": "pick_overall"})
        if pick_cell is None or not pick_cell.get_text(strip=True).isdigit():
            continue
        pick = int(pick_cell.get_text(strip=True))

        player_cell = row.find("td", {"data-stat": "player"})
        if player_cell is None or not player_cell.get_text(strip=True):
            continue
        link = player_cell.find("a", href=True)
        m = re.search(r"/players/\w/(\w+)\.html", link["href"]) if link else None
        bbref_id = m.group(1) if m else None  # None => never played in the NBA

        team_cell = row.find("td", {"data-stat": "team_id"})
        school_cell = row.find("td", {"data-stat": "college_name"})
        school = school_cell.get_text(strip=True) if school_cell else ""

        picks.append({
            "full_name": player_cell.get_text(strip=True),
            "bbref_id": bbref_id,
            "draft_year": year,
            "draft_pick": pick,
            "draft_team": team_cell.get_text(strip=True) if team_cell else None,
            "draft_tier": tier_for_pick(pick),
            # No college listed = international / non-college pathway (refine later)
            "prospect_source": "college" if school else "international",
            "pre_draft_school": school or None,
            # Never reached the NBA => outcome is already known (0 games)
            "outcomes_checked": 1 if bbref_id is None else 0,
        })
    return picks


UPSERT = """
INSERT INTO players (full_name, bbref_id, draft_year, draft_pick, draft_team,
                     draft_tier, prospect_source, pre_draft_school, outcomes_checked)
VALUES (:full_name, :bbref_id, :draft_year, :draft_pick, :draft_team,
        :draft_tier, :prospect_source, :pre_draft_school, :outcomes_checked)
ON CONFLICT(draft_year, draft_pick) DO UPDATE SET
    full_name = excluded.full_name,
    bbref_id = excluded.bbref_id,
    draft_team = excluded.draft_team,
    draft_tier = excluded.draft_tier,
    prospect_source = excluded.prospect_source,
    pre_draft_school = excluded.pre_draft_school
"""  # outcomes_checked and hand-filled columns are never overwritten on re-runs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-cache", action="store_true", help="parse cached HTML only, no downloads")
    ap.add_argument("--years", type=int, nargs="*", default=list(range(FIRST_YEAR, LAST_YEAR + 1)))
    args = ap.parse_args()

    build_database()
    conn = sqlite3.connect(DB_PATH)
    total = 0
    try:
        for year in args.years:
            path = RAW_DIR / f"draft_{year}.html" if args.from_cache else download_year(year)
            if not path.exists():
                print(f"  {year}: no cached file, skipping")
                continue
            picks = parse_draft_page(path.read_text(encoding="utf-8"), year)
            conn.executemany(UPSERT, picks)
            conn.commit()
            print(f"{year}: {len(picks)} picks loaded")
            total += len(picks)
    finally:
        conn.close()
    print(f"Done. {total} picks processed.")


if __name__ == "__main__":
    main()
