# Draft Bust-Risk Model

A model that scores NBA draft prospects on bust risk instead of pure talent, applying risk-management thinking (quantifying downside probability) to player evaluation.

SQLite database for the NBA draft prospect bust-risk project.

## Files

- `schema.sql` — full table definitions + the `model_dataset` view (your final X+y table for scikit-learn).
- `build_db.py` — builds `draft_bust_model.db` from the schema; also contains `recompute_bust_labels()`, a Python implementation of the locked labeling rule (easier to test than a giant SQL CASE statement).
- `seed_example.py` — loads 2 example players (one clear bust, one clear non-bust) and runs the labeling rule so you can confirm the logic works before doing the real data pull.
- `draft_bust_model.db` — the actual SQLite file. Open it with any SQLite browser (e.g. [DB Browser for SQLite](https://sqlitebrowser.org/)) or query it directly from pandas.

## The locked rule (baked into `build_db.py`)

- Draft classes: 2005–2021
- A season only counts toward the outcome if `games_played >= 48`
- A player is **not** a bust if they clear their tier's BPM bar in **2 or more** of their qualifying seasons (out of their first 5 NBA seasons)
- Tier thresholds:
  | Tier | Picks | Bar |
  |---|---|---|
  | 1 | 1–5 | BPM ≥ 4.0 **and** PPG ≥ 20 |
  | 2 | 6–14 | BPM ≥ 2.0 |
  | 3 | 15–30 | BPM ≥ 0.0 |
  | 4 | 31+ | BPM ≥ -2.0 |

## Table design

- `players` — identity + draft context (draft year/pick/tier, measurables, prospect source).
- `prospect_stats` — **pre-NBA stats only**. These are your model features (X). Never put NBA outcome data here.
- `nba_outcomes` — post-draft season-by-season NBA stats, used **only** to compute the label. Not a feature source.
- `bust_labels` — derived table, one row per player, holding the final bust classification. Treat it like a materialized view: wipe and recompute with `recompute_bust_labels()` any time you load new outcome data or change the rule (bump `label_version` if you ever change the rule itself, so old labels aren't lost).
- `model_dataset` — a SQL view that joins `players` + `prospect_stats` + `bust_labels` into one row per player, ready to load into pandas for scikit-learn.

## Workflow

1. Load `players` and `prospect_stats` rows as you scrape/clean pre-draft data (Basketball-Reference draft pages, Sports-Reference CBB, Bart Torvik, KenPom, etc.).
2. Load `nba_outcomes` rows (Basketball-Reference per-season BPM/games/PPG for each player's first 5 NBA seasons).
3. Run `recompute_bust_labels()` to populate `bust_labels`.
4. Pull your modeling table straight from the view:

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("draft_bust_model.db")
df = pd.read_sql("SELECT * FROM model_dataset WHERE is_bust IS NOT NULL", conn)
conn.close()
```

That `df` is your clean, feature-complete, leakage-free training set — every column starting with `prospect_` or the measurables/context columns is a legal feature; `is_bust` is your target.

## Try it yourself

```bash
python3 build_db.py       # creates draft_bust_model.db from schema.sql
python3 seed_example.py   # loads 2 example players and runs the labeling rule
```
