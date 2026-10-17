"""Central configuration: paths and tunable thresholds (NF-04: no magic numbers in code)."""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("AEI_DATA_DIR", ROOT_DIR / "synthetic_microbiology_dataset"))

# Surveillance rules (PROJECT.md §5)
MIN_ISOLATES_FOR_PERCENT = 30
HOSPITAL_ACQUIRED_MIN_DAYS = 2  # sample_date - admission_date >= 2 → hospital day 3 or later

# Time windows (DATA-04)
RECENT_WINDOW_DAYS = 28
ANNUAL_WINDOW_DAYS = 365
