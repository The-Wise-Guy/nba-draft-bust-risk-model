"""
build_db.py
-----------
1. Creates draft_bust_model.db from schema.sql (idempotent — safe to re-run).
2. Provides `recompute_bust_labels()` which implements the locked labeling
   rule in plain Python (easier to test/debug than a single SQL CASE tree).

Run standalone to (re)build an empty database:
    python3 build_db.py

Import and call after loading players/prospect_stats/nba_outcomes:
    from build_db import recompute_bust_labels
    recompute_bust_labels("draft_bust_model.db")
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "draft_bust_model.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Locked tier thresholds (see schema.sql header for the full rule)
TIER_THRESHOLDS = {
    1: {"bpm": 4.0, "ppg": 20.0},   # picks 1-5: BPM >= 4.0 AND PPG >= 20
    2: {"bpm": 2.0, "ppg": None},   # picks 6-14
    3: {"bpm": 0.0, "ppg": None},   # picks 15-30
    4: {"bpm": -2.0, "ppg": None},  # picks 31+ (2nd round)
}
MIN_QUALIFYING_GAMES = 48
SEASONS_NEEDED_TO_CLEAR_BAR = 2


def build_database(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        with open(schema_path, "r") as f:
            conn.executescript(f.read())
        conn.commit()
        print(f"Database ready at {db_path}")
    finally:
        conn.close()


def _clears_bar(tier: int, bpm: float, ppg: float | None) -> bool:
    t = TIER_THRESHOLDS[tier]
    if bpm is None:
        return False
    if t["ppg"] is not None:
        return bpm >= t["bpm"] and (ppg is not None and ppg >= t["ppg"])
    return bpm >= t["bpm"]


def recompute_bust_labels(db_path: Path = DB_PATH, label_version: str = "v1") -> int:
    """
    Recomputes bust_labels for every player who has NBA outcome rows.
    Returns the number of players labeled.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.player_id, p.draft_tier, o.games_played, o.box_plus_minus, o.pts_per_game
            FROM players p
            JOIN nba_outcomes o ON o.player_id = p.player_id
            ORDER BY p.player_id
        """)
        rows = cur.fetchall()

        by_player: dict[int, dict] = {}
        for r in rows:
            pid = r["player_id"]
            by_player.setdefault(pid, {"tier": r["draft_tier"], "seasons": []})
            by_player[pid]["seasons"].append(
                {"games": r["games_played"], "bpm": r["box_plus_minus"], "ppg": r["pts_per_game"]}
            )

        cur.execute("DELETE FROM bust_labels WHERE label_version = ?", (label_version,))

        count = 0
        for pid, data in by_player.items():
            tier = data["tier"]
            qualifying = [s for s in data["seasons"] if (s["games"] or 0) >= MIN_QUALIFYING_GAMES]
            seasons_meeting_bar = sum(
                1 for s in qualifying if _clears_bar(tier, s["bpm"], s["ppg"])
            )
            is_bust = 0 if seasons_meeting_bar >= SEASONS_NEEDED_TO_CLEAR_BAR else 1

            cur.execute("""
                INSERT INTO bust_labels
                    (player_id, draft_tier, qualifying_seasons, seasons_meeting_bar, is_bust, label_version)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (pid, tier, len(qualifying), seasons_meeting_bar, is_bust, label_version))
            count += 1

        conn.commit()
        print(f"Labeled {count} players (rule version: {label_version})")
        return count
    finally:
        conn.close()


if __name__ == "__main__":
    build_database()
