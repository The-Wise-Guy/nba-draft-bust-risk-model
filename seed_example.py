"""
seed_example.py
---------------
Demonstrates the data-loading pattern with a couple of real players,
then runs the labeling rule so you can sanity-check the logic before
committing to the full 2005-2021 pull.

Run:
    python3 seed_example.py
"""

import sqlite3
from build_db import DB_PATH, build_database, recompute_bust_labels

build_database()  # no-op if already built

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# --- Example 1: a clear non-bust (Tier 1 pick who hit the bar) ---
cur.execute("""
    INSERT OR IGNORE INTO players
        (full_name, bbref_id, draft_year, draft_pick, draft_team, draft_tier,
         position, height_in, prospect_source, competition_tier, class_year)
    VALUES
        ('Example Star', 'examplst01', 2015, 3, 'Example Team', 1,
         'SF', 80, 'college', 'power6', 'Freshman')
""")
star_id = cur.execute(
    "SELECT player_id FROM players WHERE bbref_id = 'examplst01'"
).fetchone()[0]

cur.execute("""
    INSERT OR IGNORE INTO prospect_stats
        (player_id, season_label, team_or_club, games_played, minutes_per_game,
         pts_per_game, reb_per_game, ast_per_game, usage_rate, true_shooting_pct)
    VALUES (?, 'Final Season', 'Example U', 35, 33.0, 19.5, 7.0, 2.5, 28.5, 0.58)
""", (star_id,))

# Two qualifying seasons that clear the Tier 1 bar (BPM>=4.0 AND PPG>=20)
for season_num, year, bpm, ppg, games in [
    (1, "2015-16", 1.5, 12.0, 70),
    (2, "2016-17", 4.5, 21.0, 74),   # clears
    (3, "2017-18", 5.2, 24.0, 68),   # clears
    (4, "2018-19", 6.0, 26.0, 72),
    (5, "2019-20", 6.5, 27.0, 60),
]:
    cur.execute("""
        INSERT OR IGNORE INTO nba_outcomes
            (player_id, nba_season_number, season_year, games_played, box_plus_minus, pts_per_game)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (star_id, season_num, year, games, bpm, ppg))

# --- Example 2: a clear Tier 1 bust (never sustains the bar) ---
cur.execute("""
    INSERT OR IGNORE INTO players
        (full_name, bbref_id, draft_year, draft_pick, draft_team, draft_tier,
         position, height_in, prospect_source, competition_tier, class_year)
    VALUES
        ('Example Bust', 'examplbu01', 2015, 4, 'Example Team 2', 1,
         'PF', 82, 'college', 'power6', 'Sophomore')
""")
bust_id = cur.execute(
    "SELECT player_id FROM players WHERE bbref_id = 'examplbu01'"
).fetchone()[0]

cur.execute("""
    INSERT OR IGNORE INTO prospect_stats
        (player_id, season_label, team_or_club, games_played, minutes_per_game,
         pts_per_game, reb_per_game, ast_per_game, usage_rate, true_shooting_pct)
    VALUES (?, 'Final Season', 'Example State', 32, 30.0, 16.0, 8.5, 1.0, 24.0, 0.53)
""", (bust_id,))

for season_num, year, bpm, ppg, games in [
    (1, "2015-16", -1.0, 6.0, 55),
    (2, "2016-17", 0.5, 8.5, 40),   # doesn't qualify — only 40 games
    (3, "2017-18", -0.5, 7.0, 62),
    (4, "2018-19", 1.0, 9.0, 58),
    (5, "2019-20", -2.0, 5.0, 20),  # doesn't qualify — too few games
]:
    cur.execute("""
        INSERT OR IGNORE INTO nba_outcomes
            (player_id, nba_season_number, season_year, games_played, box_plus_minus, pts_per_game)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (bust_id, season_num, year, games, bpm, ppg))

conn.commit()
conn.close()

# --- Run the labeling rule and show results ---
recompute_bust_labels()

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("""
    SELECT p.full_name, p.draft_tier, bl.qualifying_seasons, bl.seasons_meeting_bar, bl.is_bust
    FROM bust_labels bl JOIN players p ON p.player_id = bl.player_id
""")
print("\nLabel results:")
for row in cur.fetchall():
    label = "BUST" if row["is_bust"] else "NOT A BUST"
    print(f"  {row['full_name']:15s} tier={row['draft_tier']}  "
          f"qualifying_seasons={row['qualifying_seasons']}  "
          f"cleared_bar={row['seasons_meeting_bar']}  -> {label}")
conn.close()
