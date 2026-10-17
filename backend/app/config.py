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

# --- Patients, spread, therapy and integration (slice 4) ------------------------------------

# Carrier registry (PAT-01): a patient with any isolate carrying one of these phenotypes is a
# known carrier from that sample date on. No expiry by default (None): the data covers 3 years
# and a flag is cleared only by screening, which this data does not record.
CARRIER_PHENOTYPES = ["ESBL", "MRSA", "VRE", "CPE"]
CARRIER_FLAG_DAYS: int | None = None

# Carrier re-appearance (PAT-02): a known carrier sampled on a ward raises an alert for that
# ward, unless the patient was already sampled there in the last CARRIER_REVISIT_DAYS days (the
# ward knows). Only hospital wards, where contact precautions apply; health-centre visits use
# standard precautions.
CARRIER_ALERT_INSTITUTIONS = ("hospital",)
CARRIER_REVISIT_DAYS = 30

# Resistance profiles (ANOM-05, ANOM-09): an isolate's profile is the set of agents it is
# resistant to among those tested (intrinsic resistance left out). Urine-only agents are left
# out when profiles are compared across wards and specimens, since only urine isolates get them.
PROFILE_URINE_ONLY = ("MEC", "TMP", "NIT")
PROFILE_MIN_SHARED = 3  # agents both were tested for (wound S. aureus gets only FOX, VAN, CLI)
PROFILE_BASELINE_DAYS = 365
# A cluster looks like one strain when at least this share of its cases match the dominant
# profile and that is unlikely given how common the profile is elsewhere (binomial test).
PROFILE_SAME_STRAIN_SHARE = 0.7
PROFILE_SAME_STRAIN_ALPHA = 0.01
PROFILE_MIN_BACKGROUND = 10  # background isolates needed for the comparison

# Multi-ward signal (ANOM-09): new cases of one phenotype × organism × profile on ≥ 2 wards in
# MULTIWARD_WINDOW_DAYS, significantly above the profile's hospital-wide baseline (Poisson, FDR
# across profiles that day), with the excess not confined to one ward: the cases outside the
# busiest ward must also exceed their own expected count.
MULTIWARD_WINDOW_DAYS = 28
MULTIWARD_MIN_CASES = 3
MULTIWARD_MIN_OUTSIDE_CASES = 2
MULTIWARD_OUTSIDE_ALPHA = 0.05

ALERT_TYPES["carrier"] = {
    "label": "Known carrier sampled",
    "severity": "medium",  # must not outrank clusters
    "episode_gap": 7,
    "active_days": 7,
    # Routine: ~1 per hospital ward per week. Shown to the ward and in its own inbox section, but
    # not counted in the "new alerts" badge, the replay jump list or pause-on-new-alert.
    "routine": True,
}
ALERT_TYPES["multi_ward"] = {
    "label": "Seen on several wards",
    "severity": "high",
    "episode_gap": 28,
    "active_days": 14,
}

# Spread view (V10) and "where did they go next" (PAT-03): samples of a cluster's patients on
# other wards after their case, up to this many days later.
FOLLOWUP_DAYS = 90

# Therapy helper (V2, VIEW-04): weighted-incidence syndromic antibiogram (WISCA). Coverage of an
# agent = Σ organism share × susceptibility, first isolates of the infection's specimen in the
# last 12 months, with a Bayesian interval (Dirichlet × Beta draws).
THERAPY_INFECTIONS = {
    "uti": {"label": "Urinary tract infection", "specimen": "urine"},
    "bloodstream": {"label": "Bloodstream infection", "specimen": "blood"},
    "wound": {"label": "Wound infection", "specimen": "wound"},
}
THERAPY_MIN_ISOLATES = 30  # first isolates in the population; else fall back to a broader level
THERAPY_GOOD_COVERAGE = 90.0  # mirrors the 10 % / 20 % resistance tiers
THERAPY_WARN_COVERAGE = 80.0
THERAPY_MAX_UNKNOWN_SHARE = 0.5  # agents untested on more of the population are listed apart
THERAPY_DRAWS = 4000
THERAPY_EXCLUDE = ("FOX",)  # the cefoxitin screen detects MRSA; it is not a treatment
# Reserve agents: shown, but marked, since guidelines keep them for resistant infections.
THERAPY_RESERVE = ("MEM",)
# EUCAST expert rule: S. aureus susceptibility to β-lactams other than penicillins is inferred
# from the cefoxitin screen (MSSA susceptible, MRSA resistant).
THERAPY_INFERRED = {("Staphylococcus aureus", code): "FOX" for code in ("TZP", "CXM", "CRO", "MEM")}

# Integration (API-02–05, NOTIF-03/05). Links on CDS cards point at the web app.
UI_BASE_URL = os.environ.get("AEI_UI_URL", "http://localhost:5173")
# Where this API is reachable, for the default webhook to the mock patient record (API-04).
API_BASE_URL = os.environ.get("AEI_API_URL", "http://localhost:8000")
WEBHOOK_TIMEOUT_SECONDS = 5
DIGEST_PERIODS = {"week": 7, "month": 30}

# --- Usability phase (slice 5) --------------------------------------------------------------

# Clinician "what not to use" list (UX-05). An agent is flagged for an infection when, in the
# last 12 months, one of the infection's main organisms (at least AVOID_MIN_ORGANISM_SHARE of
# first isolates) is resistant at or above EMPIRICAL_THRESHOLD_PCT, with n ≥ 30 at the most
# specific location level that has them (STAT-04). Based on resistance, not WISCA coverage:
# untested organisms (E. faecalis) would cap coverage for nearly every agent.
AVOID_MIN_ORGANISM_SHARE = 0.10
# Agents most of the infection's organisms resist intrinsically are "not suited", not "no warning".
AVOID_NOT_SUITED_SHARE = 0.5
# "Since when": the 12-month rate is recomputed at monthly steps back from the as-of date; the
# flag has held since the earliest step of the unbroken run above the limit up to today.
AVOID_SINCE_STEP_DAYS = 30
AVOID_SINCE_MAX_STEPS = 36
# Direction: last 12 months vs the 12 months before (Fisher exact), at least this many points.
AVOID_DIRECTION_MIN_PP = 5.0
AVOID_DIRECTION_ALPHA = 0.05
# What to do, per alert type, in the clinician's exceptions list (UX-05).
ALERT_ACTIONS = {
    "sentinel": "Contact precautions for the patient; infection control will advise.",
    "cluster": "Contact precautions for affected patients; infection control is investigating.",
    "multi_ward": "Contact precautions; infection control is tracing it between wards.",
    "rate_shift": "Resistance has risen here: check the avoid list before choosing empirically.",
    "novelty": "Unusual finding for this ward: infection control will review it.",
    "carrier": "Known carrier: contact precautions while on the ward.",
    "data_gap": "Lab data from here has stopped arriving: figures may be out of date.",
}

# Varha drill-down (UX-01/03): Varha → institution → ward. Hospital wards form one institution;
# each health centre is an institution of its own. Other Varha hospitals are not in the demo
# data and are shown as greyed placeholders.
VARHA_LABEL = "Varha"
VARHA_FULL = "Southwest Finland wellbeing services county"
VARHA_HOSPITAL = {"key": "tyks", "label": "Tyks", "full": "Turku University Hospital"}
VARHA_PLACEHOLDERS = ["Loimaa hospital", "Vakka-Suomi hospital", "Salo hospital"]

# ---------- Slice 5b: review fixes ----------
# A recent rise names an outbreak as its likely cause (UX-07) when at least this share of the
# patients behind the resistant isolates are cases of an active cluster or multi-ward alert on
# the same ward, and at least this many.
RISE_CAUSE_MIN_SHARE = 0.5
RISE_CAUSE_MIN_CASES = 3
# Stewardship findings (ANOM-10): owned by lab / stewardship, with their own status.
STEWARDSHIP_STATUSES = ("new", "under_review", "guideline_updated", "accepted")
STEWARDSHIP_STATUS_LABELS = {
    "new": "Not yet reviewed",
    "under_review": "Under review by stewardship",
    "guideline_updated": "Reviewed: local guideline updated",
    "accepted": "Reviewed: guideline unchanged",
}
STEWARDSHIP_KINDS = {
    "crossed": "Crossed the limit",
    "rising": "Rising, still under the limit",
    "standing": "Above the limit as far back as the data goes",
}
