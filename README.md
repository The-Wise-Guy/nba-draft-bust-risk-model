# NBA Draft Bust-Risk Model

A model that scores NBA draft prospects on bust risk instead of pure talent, applying risk-management thinking (quantifying downside probability) to player evaluation.

**Approach:** pre-draft stats and context go in (college or international production, adjusted for level of competition); a tiered bust outcome comes out, defined by what the player actually did in their first five NBA seasons.

## Project status

- [x] Database schema and bust-labeling rule
- [x] Draft-class scraper (2005-2021 picks)
- [ ] NBA outcomes scraper (first five seasons: games, PPG, BPM)
- [ ] Pre-draft stats (college and international) and competition-tier mapping
- [ ] Model: logistic regression, then random forest, validated by draft year
- [ ] Results and case-study writeup

## Definition of a bust

Busts are defined relative to draft slot, using Basketball-Reference BPM benchmarks over each player's first five NBA seasons.

| Tier | Picks | Not a bust if the player reaches... |
|---|---|---|
| 1 | 1-5 | BPM >= 4.0 **and** >= 20 PPG (All-Star caliber) |
| 2 | 6-14 | BPM >= 2.0 (good starter) |
| 3 | 15-30 | BPM >= 0.0 (decent starter / solid 6th man) |
| 4 | 31+ | BPM >= -2.0 (replacement level) |

Rules applied to every player:

- The bar must be cleared in **2 or more** of the first five NBA seasons (one hot season is noise).
- A season only counts if the player appeared in **48+ games**.
- Draft classes **2005-2021** (2021 is the latest class with a complete five-year window).
- Drafted players who never played an NBA game are labeled busts.

## Data design

| Table | Purpose |
|---|---|
| `players` | One row per drafted player: draft year, pick, tier, school or pathway, measurables |
| `prospect_stats` | **Pre-NBA stats only.** These are the model's features (X) |
| `nba_outcomes` | Post-draft seasons, used **only** to build the label. Never a feature |
| `bust_labels` | Derived bust classification (y), recomputed from the rule above |
| `model_dataset` | SQL view joining features and labels for scikit-learn |

Keeping `prospect_stats` and `nba_outcomes` separate prevents leakage: the outcome can never end up in the model's inputs.

## Files

- `schema.sql`: table definitions and the `model_dataset` view
- `build_db.py`: builds the database; `recompute_bust_labels()` applies the labeling rule
- `scrape_drafts.py`: downloads and parses the 2005-2021 draft pages into `players`
- `requirements.txt`: Python dependencies

## Run it

```bash
pip install -r requirements.txt
python3 scrape_drafts.py     # builds draft_bust_model.db and loads every pick
```

The scraper caches each page in `data/raw/`, waits between requests, and stops if the site rate-limits it. Re-running is safe.

## Loading the modeling table

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("draft_bust_model.db")
df = pd.read_sql("SELECT * FROM model_dataset WHERE is_bust IS NOT NULL", conn)
conn.close()
```

## Author

Built by Brady, who has a degree in Risk Management & Insurance from the University of South Carolina, to apply downside-risk thinking to basketball player evaluation.

