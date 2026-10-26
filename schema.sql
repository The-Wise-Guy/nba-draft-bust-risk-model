-- ============================================================
-- NBA Draft Prospect Bust-Risk Model — Database Schema (v2)
-- ============================================================
--   players         one row per drafted player (identity + draft context)
--   prospect_stats  PRE-NBA stats only -> model FEATURES (X)
--   nba_outcomes    POST-DRAFT NBA seasons -> used ONLY to build the label (y)
--   bust_labels     derived table: final bust classification per player
--   model_dataset   view joining X + y for scikit-learn
--
-- Locked labeling rule:
--   - Draft classes 2005-2021 (2021 has a complete 5-year window through 2025-26)
--   - A season only counts if games_played >= 48
--   - Not a bust = clears the tier's BPM bar in 2+ qualifying seasons
--     out of the first 5 NBA seasons
--   - Tier bars: T1 (1-5) BPM>=4.0 AND PPG>=20 | T2 (6-14) BPM>=2.0
--                T3 (15-30) BPM>=0.0           | T4 (31+)  BPM>=-2.0
--
-- v2 change: players.outcomes_checked. A drafted player who never played an
-- NBA game has ZERO rows in nba_outcomes, and must be labeled a bust. Without
-- this flag we cannot tell "never played" apart from "outcomes not loaded yet".
-- ============================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS players (
    player_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name            TEXT NOT NULL,
    bbref_id             TEXT UNIQUE,         -- NULL for drafted players who never reached the NBA
    draft_year           INTEGER NOT NULL,    -- 2005-2021
    draft_pick           INTEGER NOT NULL,    -- overall pick, 1-60
    draft_team           TEXT,
    draft_tier           INTEGER NOT NULL CHECK (draft_tier IN (1,2,3,4)),
    position             TEXT,
    height_in            INTEGER,
    wingspan_in          INTEGER,
    weight_lb            INTEGER,
    age_at_draft         REAL,
    prospect_source      TEXT NOT NULL CHECK (prospect_source IN ('college','international','other')),
    pre_draft_school     TEXT,                -- college name as listed by Basketball-Reference
    league_or_conference TEXT,
    competition_tier     TEXT,                -- e.g. power6, mid_major, low_major, intl_elite, intl_other
    class_year           TEXT,
    notes                TEXT,
    outcomes_checked     INTEGER NOT NULL DEFAULT 0 CHECK (outcomes_checked IN (0,1)),
    UNIQUE (draft_year, draft_pick)
);

CREATE INDEX IF NOT EXISTS idx_players_draft_year ON players(draft_year);
CREATE INDEX IF NOT EXISTS idx_players_tier ON players(draft_tier);

CREATE TABLE IF NOT EXISTS prospect_stats (
    prospect_stat_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id            INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    season_label         TEXT,
    team_or_club         TEXT,
    games_played         INTEGER,
    minutes_per_game     REAL,
    pts_per_game         REAL,
    reb_per_game         REAL,
    ast_per_game         REAL,
    stl_per_game         REAL,
    blk_per_game         REAL,
    tov_per_game         REAL,
    fg_pct               REAL,
    fg3_pct              REAL,
    ft_pct               REAL,
    usage_rate           REAL,
    true_shooting_pct    REAL,
    win_shares           REAL,
    box_plus_minus       REAL,
    strength_of_schedule REAL,
    UNIQUE (player_id, season_label)
);

CREATE INDEX IF NOT EXISTS idx_prospect_stats_player ON prospect_stats(player_id);

CREATE TABLE IF NOT EXISTS nba_outcomes (
    outcome_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id            INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    nba_season_number    INTEGER NOT NULL CHECK (nba_season_number BETWEEN 1 AND 5),
    season_year          TEXT NOT NULL,
    team                 TEXT,
    games_played         INTEGER NOT NULL,
    minutes_per_game     REAL,
    pts_per_game         REAL,
    box_plus_minus       REAL,
    UNIQUE (player_id, nba_season_number)
);

CREATE INDEX IF NOT EXISTS idx_nba_outcomes_player ON nba_outcomes(player_id);

CREATE TABLE IF NOT EXISTS bust_labels (
    player_id            INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    draft_tier           INTEGER NOT NULL,
    qualifying_seasons   INTEGER NOT NULL,
    seasons_meeting_bar  INTEGER NOT NULL,
    is_bust              INTEGER NOT NULL CHECK (is_bust IN (0,1)),
    label_version        TEXT NOT NULL DEFAULT 'v1',
    computed_at          TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (player_id, label_version)
);

CREATE VIEW IF NOT EXISTS model_dataset AS
SELECT
    p.player_id, p.full_name, p.draft_year, p.draft_pick, p.draft_tier,
    p.position, p.height_in, p.wingspan_in, p.weight_lb, p.age_at_draft,
    p.prospect_source, p.competition_tier, p.class_year,
    ps.games_played AS prospect_games, ps.minutes_per_game AS prospect_mpg,
    ps.pts_per_game, ps.reb_per_game, ps.ast_per_game, ps.stl_per_game,
    ps.blk_per_game, ps.tov_per_game, ps.fg_pct, ps.fg3_pct, ps.ft_pct,
    ps.usage_rate, ps.true_shooting_pct, ps.win_shares,
    ps.box_plus_minus AS prospect_bpm,
    bl.is_bust
FROM players p
LEFT JOIN prospect_stats ps ON ps.player_id = p.player_id
LEFT JOIN bust_labels bl    ON bl.player_id = p.player_id AND bl.label_version = 'v1';
