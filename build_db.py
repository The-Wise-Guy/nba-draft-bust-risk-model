"""
build_db.py
-----------
build_database()         creates draft_bust_model.db from schema.sql (idempotent)
tier_for_pick(pick)      draft pick -> tier 1-4
recompute_bust_labels()  applies the locked labeling rule

Only players with outcomes_checked = 1 get labeled. A checked player with no
rows in nba_outcomes never played an NBA game, so they have 0 qualifying
seasons and come out as a bust.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "draft_bust_model.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

TIER_THRESHOLDS = {
    1: {"bpm": 4.0, "ppg": 20.0},   # picks 1-5
    2: {"bpm": 2.0, "ppg": None},   # picks 6-14
    3: {"bpm": 0.0, "ppg": None},   # picks 15-30
    4: {"bpm": -2.0, "ppg": None},  # picks 31+
}
MIN_QUALIFYING_GAMES = 48
SEASONS_NEEDED_TO_CLEAR_BAR = 2
LAST_COMPLETE_CLASS = 2021  # 5-year window complete through the 2025-26 season


def tier_for_pick(pick: int) -> int:
    if pick <= 5:
        return 1
    if pick <= 14:
        return 2
    if pick <= 30:
        return 3
    return 4


def build_database(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(Path(schema_path).read_text())
        conn.commit()
        print(f"Database ready at {db_path}")
    finally:
        conn.close()


def _clears_bar(tier: int, bpm, ppg) -> bool:
    if bpm is None:
        return False
    t = TIER_THRESHOLDS[tier]
    if t["ppg"] is not None:
        return bpm >= t["bpm"] and ppg is not None and ppg >= t["ppg"]
    return bpm >= t["bpm"]


def recompute_bust_labels(db_path: Path = DB_PATH, label_version: str = "v1") -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        players = cur.execute(
            "SELECT player_id, draft_tier FROM players "
            "WHERE outcomes_checked = 1 AND draft_year <= ?",
            (LAST_COMPLETE_CLASS,),
        ).fetchall()

        cur.execute("DELETE FROM bust_labels WHERE label_version = ?", (label_version,))

        for p in players:
            seasons = cur.execute(
                "SELECT games_played, box_plus_minus, pts_per_game "
                "FROM nba_outcomes WHERE player_id = ?",
                (p["player_id"],),
            ).fetchall()
            qualifying = [s for s in seasons if (s["games_played"] or 0) >= MIN_QUALIFYING_GAMES]
            met = sum(
                1 for s in qualifying
                if _clears_bar(p["draft_tier"], s["box_plus_minus"], s["pts_per_game"])
            )
            is_bust = 0 if met >= SEASONS_NEEDED_TO_CLEAR_BAR else 1
            cur.execute(
                "INSERT INTO bust_labels (player_id, draft_tier, qualifying_seasons, "
                "seasons_meeting_bar, is_bust, label_version) VALUES (?,?,?,?,?,?)",
                (p["player_id"], p["draft_tier"], len(qualifying), met, is_bust, label_version),
            )

        conn.commit()
        print(f"Labeled {len(players)} players (rule version: {label_version})")
        return len(players)
    finally:
        conn.close()


if __name__ == "__main__":
    build_database()


if __name__ == "__main__":
    build_database()
