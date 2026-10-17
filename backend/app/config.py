"""Central configuration: paths and tunable thresholds (NF-04: no magic numbers in code)."""

import os
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("AEI_DATA_DIR", ROOT_DIR / "synthetic_microbiology_dataset"))

# Scenario "today": the default as-of date when a request doesn't set one (LIVE-01). By default
# it is the last sample date in the data, so it moves forward as new data is ingested (DATA-05).
# AEI_AS_OF pins it to a fixed date instead.
AS_OF_OVERRIDE = date.fromisoformat(v) if (v := os.environ.get("AEI_AS_OF")) else None

# Simulated lab feed (DATA-05): with AEI_HOLD_BACK_FROM set, samples from that date on are held
# back at startup and can be received day by day through the ingestion path, as from a live LIS.
HOLD_BACK_FROM = date.fromisoformat(v) if (v := os.environ.get("AEI_HOLD_BACK_FROM")) else None

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

# --- Alerts and detectors (slice 2) ---------------------------------------------------------

# Triage state (NOTIF-06) is kept in a small JSON file, outside the dataset.
STATE_DIR = Path(os.environ.get("AEI_STATE_DIR", ROOT_DIR / "backend" / ".state"))

PHENOTYPES = ["ESBL", "MRSA", "VRE", "CPE"]  # isolate flag columns (lower-case in the data)
ENTEROBACTERALES = frozenset(
    {
        "Escherichia coli",
        "Klebsiella pneumoniae",
        "Klebsiella oxytoca",
        "Proteus mirabilis",
        "Citrobacter freundii",
    }
)

# Sentinel events (NOTIF-01): one case = one alert, no statistics. Checked in this order;
# an isolate matching several rules gets one alert listing every reason.
# Meropenem R is limited to Enterobacterales: Pseudomonas has a ~6 % background (DATA_NOTES).
SENTINEL_RULES = [
    {"key": "CPE", "label": "CPE (carbapenemase-producing Enterobacterales)", "phenotype": "CPE"},
    {"key": "VRE", "label": "VRE (vancomycin-resistant enterococcus)", "phenotype": "VRE"},
    {
        "key": "CRE",
        "label": "Meropenem-resistant Enterobacterales",
        "antibiotic": "MEM",
        "organisms": ENTEROBACTERALES,
    },
    {"key": "VAN-R", "label": "Vancomycin resistance", "antibiotic": "VAN"},
]

# Multiple-testing control (STAT-08): Benjamini–Hochberg false-discovery rate, applied across
# all hypotheses tested on the same evaluation day.
FDR_Q = 0.05
# Statistical detectors compare against a baseline period; they don't test before this much
# history exists (the first months of the data).
MIN_BASELINE_DAYS = 182

# Outbreak / cluster (ANOM-01): new phenotype cases per ward in a short window vs the ward's own
# baseline rate. Poisson test; evaluated daily on days with a new case.
CLUSTER_WINDOW_DAYS = 14
CLUSTER_BASELINE_DAYS = 365  # ends the day before the window starts
CLUSTER_MIN_CASES = 3
CLUSTER_CASE_DEDUP_DAYS = 90  # repeat positives of the same patient within this count once
CLUSTER_BASELINE_PSEUDOCOUNT = 0.5  # keeps the expected count > 0 on wards with no history

# Resistance-rate shift (ANOM-02): last 4 weeks vs the 12 months before, first isolates per
# ward × specimen × organism. One-sided Fisher exact test; evaluated weekly (end of ISO week).
RATE_SHIFT_MIN_RECENT_N = 10
RATE_SHIFT_MIN_BASELINE_N = 30
RATE_SHIFT_MIN_INCREASE_PP = 10.0  # percentage points: ignore tiny but "significant" shifts
RATE_SHIFT_EVAL_WEEKDAY = 6  # Sunday (Monday = 0)

# Data-quality gap (ANOM-04): the silence test of the freshness badge, plus a low-volume test on
# the last 7 days vs the 8 weeks before (Poisson lower tail). Alerts need much stronger evidence
# than the badge: ~10,000 ward-days are tested over 3 years, and daily volumes vary more than
# Poisson (α = 0.001 would raise ~30 alerts, nearly all ordinary dips).
GAP_ALERT_ALPHA = 1e-6
GAP_VOLUME_WINDOW_DAYS = 7

# Novelty (ANOM-08): a phenotype not seen on the ward for this long (or ever, given at least this
# much history). CPE/VRE are sentinels already; their alerts carry the same "first in N days" note.
NOVELTY_MIN_GAP_DAYS = 180
NOVELTY_PHENOTYPES = ["ESBL", "MRSA"]
# Organisms rarer than this share of all isolates so far also get novelty alerts. (None of the
# 9 organisms in the current data is this rare.)
NOVELTY_RARE_ORGANISM_MAX_SHARE = 0.01

# Alert lifecycle and severity (NOTIF-04). Firings of the same detector, ward and subject that
# are at most EPISODE_GAP days apart form one alert; it stays active ACTIVE_DAYS after its last
# firing, then counts as resolved.
ALERT_TYPES = {
    "sentinel": {
        "label": "Sentinel case",
        "severity": "critical",
        "episode_gap": 28,
        "active_days": 28,
    },
    "cluster": {
        "label": "Outbreak / cluster",
        "severity": "high",
        "episode_gap": 28,
        "active_days": 14,
    },
    "rate_shift": {
        "label": "Resistance shift",
        "severity": "medium",
        "episode_gap": 14,
        "active_days": 6,  # weekly evaluation: resolves at the next one unless it fires again
    },
    "novelty": {
        "label": "Not seen here recently",
        "severity": "medium",
        "episode_gap": 0,
        "active_days": 28,
    },
    "data_gap": {
        "label": "Data gap",
        "severity": "medium",
        "episode_gap": 3,
        "active_days": 0,  # active only while the gap lasts
    },
}
SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
# Dismissing an alert suppresses new alerts with the same detector, ward and subject that start
# within this many days of the dismissed one's last firing (NOTIF-06).
DISMISS_SUPPRESS_DAYS = 90
# How far back the inbox looks for resolved alerts when asked to include them.
RESOLVED_LOOKBACK_DAYS = 90

# --- Replay, trends and subgroups (slice 3) -------------------------------------------------

# Replay (LIVE-04): "jump to event" starts this many days before the event's first case.
REPLAY_LEAD_DAYS = 7

# Slow drift (ANOM-03): Cochran–Armitage test for a linear trend in resistance over calendar
# quarters (first isolates per quarter), for every location × specimen × organism × antibiotic.
# Gates keep thin series out; FDR across all series tested (STAT-08).
TREND_MIN_QUARTERS = 6  # quarters with at least one isolate
TREND_MIN_TOTAL_N = 100
TREND_MIN_CHANGE_PP = 5.0  # fitted change over the whole period, percentage points
# Empirical-use threshold (PROJECT.md §5): a commonly used upper limit for choosing an
# antibiotic empirically. Trend charts draw it; crossing it is reported as a finding.
EMPIRICAL_THRESHOLD_PCT = 20.0

# Subgroup-difference discovery (STAT-09): resistance compared across the levels of each
# dimension (chi-square, or Fisher exact for two levels), first isolates in the window. Levels
# with fewer than SUBGROUP_MIN_N isolates are left out. FDR across all comparisons (STAT-08).
SUBGROUP_DIMENSIONS = {
    "sex": "Sex",
    "age_band": "Age band",
    "hospital_acquired": "Hospital-acquired",
    "ward_type": "Inpatient / outpatient",
    "home_area": "Home area",
    "ward_code": "Ward",
}
SUBGROUP_MIN_N = 30
SUBGROUP_MIN_DIFF_PP = 5.0

# Clinically known splits shown by default in My Ward (STAT-07): sub-rows for this organism
# and specimen by this dimension (urine E. coli: men have about twice the CIP resistance).
DEFAULT_SPLITS = [{"specimen": "urine", "organism": "Escherichia coli", "by": "sex"}]

# Ward × time overview (V5): key resistance indicators offered next to the phenotype counts.
# These follow the EARS-Net headline indicators (3rd-gen cephalosporin and fluoroquinolone
# resistance in E. coli and K. pneumoniae, MRSA), adapted to the agents in this data.
HEATMAP_KEY_RATES = [
    {"specimen": "urine", "organism": "Escherichia coli", "antibiotic": "CRO"},
    {"specimen": "urine", "organism": "Escherichia coli", "antibiotic": "CIP"},
    {"specimen": "urine", "organism": "Escherichia coli", "antibiotic": "TMP"},
    {"specimen": "urine", "organism": "Klebsiella pneumoniae", "antibiotic": "CRO"},
    {"specimen": "wound", "organism": "Staphylococcus aureus", "antibiotic": "FOX"},
]
