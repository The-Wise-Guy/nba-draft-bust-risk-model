-- ============================================================
-- NBA Draft Prospect Bust-Risk Model — Database Schema
-- ============================================================
-- Design notes:
--   * "players" holds one row per drafted player (identity + draft context).
--   * "prospect_stats" holds PRE-NBA stats only — these are your
--     model FEATURES (X). One row per player per pre-draft season
--     (usually just their final college/international season, but
--     the table supports multiple seasons if you want a multi-year
--     feature history later).
--   * "nba_outcomes" holds POST-DRAFT NBA season stats — used only
--     to calculate the bust LABEL (y). Never feed these into the
--     model as features; that would leak the outcome into the input.
--   * "bust_labels" is a derived/computed table: one row per player,
--     holding the final tier + bust classification, calculated from
--     nba_outcomes using the locked rule (see below). Recompute this
--     table any time the rule or the underlying data changes —
--     treat it as a materialized view, not hand-entered data.
--
-- Locked labeling rule (as of Sept 2026):
--   - Draft class range: 2005-2021 (2021 is the most recent class
--     with a complete 5-year outcome window through 2025-26).
--   - A season only "counts" toward the outcome if games_played >= 48.
--   - A player avoids the bust label if they clear their tier's BPM
--     threshold in at least 2 of their qualifying seasons (out of
--     their first 5 NBA seasons).
--   - Tier BPM thresholds (by draft pick):
--       Tier 1 (picks 1-5):   BPM >= 4.0 AND PPG >= 20.0
--       Tier 2 (picks 6-14):  BPM >= 2.0
--       Tier 3 (picks 15-30): BPM >= 0.0
--       Tier 4 (picks 31+):   BPM >= -2.0
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- 1. PLAYERS — one row per drafted player
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    player_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name           TEXT NOT NULL,
    bbref_id            TEXT UNIQUE,          -- Basketball-Reference player code, e.g. 'jamesle01'
    draft_year          INTEGER NOT NULL,     -- 2005-2021
    draft_pick          INTEGER NOT NULL,     -- overall pick number, 1-60
    draft_team          TEXT,
    draft_tier          INTEGER NOT NULL CHECK (draft_tier IN (1,2,3,4)),
    position            TEXT,                 -- primary position at time of draft
    height_in           INTEGER,              -- inches
    wingspan_in         INTEGER,              -- inches, if available
    weight_lb           INTEGER,
    age_at_draft        REAL,
    prospect_source     TEXT NOT NULL CHECK (prospect_source IN ('college','international','other')),
    league_or_conference TEXT,                -- e.g. 'ACC', 'EuroLeague', 'Australian NBL'
    competition_tier    TEXT,                 -- e.g. 'power6', 'mid_major', 'low_major', 'intl_elite', 'intl_other'
    class_year          TEXT,                 -- 'Freshman','Sophomore','Junior','Senior','International','G-League' etc.
    notes               TEXT
);

CREATE INDEX IF NOT EXISTS idx_players_draft_year ON players(draft_year);
CREATE INDEX IF NOT EXISTS idx_players_tier ON players(draft_tier);

-- ------------------------------------------------------------
-- 2. PROSPECT_STATS — PRE-NBA stats (model features / X)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prospect_stats (
    prospect_stat_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id           INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    season_label        TEXT,                 -- e.g. '2019-20', or 'Final Season'
    team_or_club        TEXT,
    games_played        INTEGER,
    minutes_per_game    REAL,
    pts_per_game        REAL,
    reb_per_game        REAL,
    ast_per_game        REAL,
    stl_per_game        REAL,
    blk_per_game        REAL,
    tov_per_game        REAL,
    fg_pct              REAL,
    fg3_pct             REAL,
    ft_pct              REAL,
    usage_rate          REAL,
    true_shooting_pct   REAL,
    win_shares          REAL,                 -- college/international WS if available
    box_plus_minus      REAL,                 -- pre-NBA BPM if available (e.g. college BPM from Bart Torvik)
    strength_of_schedule REAL,                -- if pulled from KenPom/Torvik
    UNIQUE(player_id, season_label)
);

CREATE INDEX IF NOT EXISTS idx_prospect_stats_player ON prospect_stats(player_id);

-- ------------------------------------------------------------
-- 3. NBA_OUTCOMES — POST-DRAFT stats, used ONLY to build the label (y)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nba_outcomes (
    outcome_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id           INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    nba_season_number   INTEGER NOT NULL CHECK (nba_season_number BETWEEN 1 AND 5),  -- 1st-5th season since draft
    season_year         TEXT NOT NULL,        -- e.g. '2021-22'
    team                TEXT,
    games_played        INTEGER NOT NULL,
    minutes_per_game    REAL,
    pts_per_game        REAL,
    box_plus_minus      REAL,                 -- NBA BPM for this season — used to check tier threshold
    qualifies           INTEGER GENERATED ALWAYS AS (CASE WHEN games_played >= 48 THEN 1 ELSE 0 END) VIRTUAL,
    UNIQUE(player_id, nba_season_number)
);

CREATE INDEX IF NOT EXISTS idx_nba_outcomes_player ON nba_outcomes(player_id);

-- ------------------------------------------------------------
-- 4. BUST_LABELS — derived table: final label per player (target y)
-- ------------------------------------------------------------
-- Recompute this from nba_outcomes + players any time the rule or
-- data changes. See label_players.py for the Python version of this
-- logic (easier to unit-test than a giant SQL CASE statement).
CREATE TABLE IF NOT EXISTS bust_labels (
    player_id             INTEGER PRIMARY KEY REFERENCES players(player_id) ON DELETE CASCADE,
    draft_tier            INTEGER NOT NULL,
    qualifying_seasons    INTEGER NOT NULL,   -- how many seasons had games_played >= 48
    seasons_meeting_bar   INTEGER NOT NULL,   -- of the qualifying seasons, how many cleared the tier's BPM bar
    is_bust               INTEGER NOT NULL CHECK (is_bust IN (0,1)),  -- 1 = bust, 0 = not a bust
    label_version         TEXT NOT NULL DEFAULT 'v1',  -- bump this if the rule changes, keep history
    computed_at           TEXT DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- Convenience view: full modeling table (X + y joined)
-- ------------------------------------------------------------
CREATE VIEW IF NOT EXISTS model_dataset AS
SELECT
    p.player_id,
    p.full_name,
    p.draft_year,
    p.draft_pick,
    p.draft_tier,
    p.position,
    p.height_in,
    p.wingspan_in,
    p.weight_lb,
    p.age_at_draft,
    p.prospect_source,
    p.competition_tier,
    p.class_year,
    ps.games_played      AS prospect_games,
    ps.minutes_per_game  AS prospect_mpg,
    ps.pts_per_game,
    ps.reb_per_game,
    ps.ast_per_game,
    ps.stl_per_game,
    ps.blk_per_game,
    ps.tov_per_game,
    ps.fg_pct,
    ps.fg3_pct,
    ps.ft_pct,
    ps.usage_rate,
    ps.true_shooting_pct,
    ps.win_shares,
    ps.box_plus_minus    AS prospect_bpm,
    bl.is_bust,
    bl.draft_tier         AS label_tier
FROM players p
LEFT JOIN prospect_stats ps ON ps.player_id = p.player_id
LEFT JOIN bust_labels bl    ON bl.player_id = p.player_id;
