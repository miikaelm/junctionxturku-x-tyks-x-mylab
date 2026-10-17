"""Central configuration: paths and tunable thresholds (NF-04: no magic numbers in code)."""

import os
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("AEI_DATA_DIR", ROOT_DIR / "synthetic_microbiology_dataset"))

# Scenario "today": the default as-of date when a request doesn't set one (LIVE-01).
DEFAULT_AS_OF = date.fromisoformat(os.environ.get("AEI_AS_OF", "2026-09-27"))

# Surveillance rules (PROJECT.md §5)
MIN_ISOLATES_FOR_PERCENT = 30
HOSPITAL_ACQUIRED_MIN_DAYS = 2  # sample_date - admission_date >= 2 → hospital day 3 or later
CI_LEVEL = 0.95  # Wilson interval (STAT-02)

# Time windows (DATA-04)
RECENT_WINDOW_DAYS = 28
ANNUAL_WINDOW_DAYS = 365

# Age bands for filtering / stratification: (label, min_age, max_age) inclusive
AGE_BANDS = [
    ("0-17", 0, 17),
    ("18-64", 18, 64),
    ("65-79", 65, 79),
    ("80+", 80, 200),
]

# Traffic-light colouring of resistance % (VIEW-09). Upper bounds, exclusive.
# 20 % is the commonly used empirical-therapy limit (PROJECT.md §5).
RESISTANCE_GOOD_BELOW = 10.0
RESISTANCE_WARN_BELOW = 20.0

# Data freshness (VIEW-12): a ward is stale when the silence since its last sample would be
# this unlikely under its recent daily sample rate (Poisson): P(0 samples in d days) < alpha.
FRESHNESS_ALPHA = 0.001  # → "stale"
FRESHNESS_WARN_ALPHA = 0.01  # → "delayed"
FRESHNESS_RATE_LOOKBACK_DAYS = 56
