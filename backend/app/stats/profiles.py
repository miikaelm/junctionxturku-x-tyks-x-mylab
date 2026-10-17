"""Resistance profiles: which agents an isolate is resistant to (ANOM-05, ANOM-09, V10).

A profile is the set of agents an isolate is resistant to among the agents it was tested for,
with intrinsic resistance left out (it says nothing about the strain). Two isolates *match*
when they agree on every agent both were tested for (at least PROFILE_MIN_SHARED of them), so a
urine isolate (tested for TMP) can match a blood isolate (not tested) of the same strain.
`core` profiles leave out the urine-only agents altogether, for grouping across specimens.

Matching profiles are a hint, not proof, of one strain: common profiles (e.g. "ESBL E. coli,
R: AMP CXM CRO") are shared by unrelated isolates. That is why a cluster's profile is compared
with how common it is elsewhere.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations

import pandas as pd
from scipy.stats import binom

from app.config import (
    PROFILE_BASELINE_DAYS,
    PROFILE_MIN_BACKGROUND,
    PROFILE_MIN_SHARED,
    PROFILE_SAME_STRAIN_ALPHA,
    PROFILE_SAME_STRAIN_SHARE,
    PROFILE_URINE_ONLY,
)
from app.data.dataset import Dataset
from app.data.intrinsic import is_intrinsic


@dataclass(frozen=True)
class Profile:
    tested: frozenset[str]
    resistant: frozenset[str]

    @property
    def key(self) -> str:
        return ",".join(sorted(self.resistant)) or "-"

    @property
    def label(self) -> str:
        return f"R: {', '.join(sorted(self.resistant))}" if self.resistant else "no acquired R"

    def shared(self, other: "Profile") -> frozenset[str]:
        return self.tested & other.tested

    def matches(self, other: "Profile") -> bool:
        both = self.shared(other)
        return len(both) >= PROFILE_MIN_SHARED and self.resistant & both == other.resistant & both

    def agreement(self, other: "Profile") -> float | None:
        both = self.shared(other)
        if len(both) < PROFILE_MIN_SHARED:
            return None
        return 1 - len((self.resistant ^ other.resistant) & both) / len(both)


def profiles(ds: Dataset, isolate_ids, *, core: bool = False) -> dict[str, Profile]:
    """Profile per isolate id (isolates without results get an empty profile)."""
    ast = ds.ast[ds.ast.isolate_id.isin(isolate_ids)]
    keep = [not is_intrinsic(o, a) for o, a in zip(ast.organism, ast.antibiotic_code)]
    ast = ast[keep]
    if core:
        ast = ast[~ast.antibiotic_code.isin(PROFILE_URINE_ONLY)]
    tested = ast.groupby("isolate_id").antibiotic_code.agg(frozenset)
    resistant = ast[ast.resistant].groupby("isolate_id").antibiotic_code.agg(frozenset)
    empty: frozenset[str] = frozenset()
    return {
        i: Profile(tested.get(i, empty), resistant.get(i, empty)) for i in pd.unique(isolate_ids)
    }


def profile_keys(ds: Dataset, isolate_ids, *, core: bool = True) -> pd.Series:
    """Profile key per isolate id ("AMP,CIP,CRO,CXM"; "-" when resistant to nothing tested)."""
    return pd.Series({i: p.key for i, p in profiles(ds, isolate_ids, core=core).items()}, dtype=str)


def cluster_similarity(
    ds: Dataset, isolate_ids: list[str], phenotype: str | None, window_start: date
) -> dict | None:
    """How alike the cases of a cluster are (ANOM-05), and whether their shared profile is
    unusual: the share of the cluster matching its dominant profile vs the share of the same
    phenotype × organism matching it elsewhere in the PROFILE_BASELINE_DAYS before the cluster."""
    iso = ds.isolates[ds.isolates.isolate_id.isin(isolate_ids)]
    if len(iso) < 2:
        return None
    organism = iso.organism.value_counts().index[0]
    cases = iso[iso.organism.eq(organism)]
    profs = profiles(ds, cases.isolate_id)
    counts = Counter(p.key for p in profs.values())
    dominant_key = max(counts, key=lambda k: (counts[k], k.count(",")))
    reference = max(
        (p for p in profs.values() if p.key == dominant_key), key=lambda p: len(p.tested)
    )
    matching = [i for i, p in profs.items() if p.matches(reference)]
    pairs = [a.agreement(b) for a, b in combinations(profs.values(), 2)]
    pairs = [x for x in pairs if x is not None]

    # Background: first isolate per patient of the same phenotype × organism, all wards.
    start = pd.Timestamp(window_start - timedelta(days=PROFILE_BASELINE_DAYS))
    bg = ds.isolates[
        ds.isolates.organism.eq(organism)
        & ds.isolates.sample_date.between(start, pd.Timestamp(window_start - timedelta(days=1)))
        & ~ds.isolates.isolate_id.isin(isolate_ids)
    ]
    if phenotype:
        bg = bg[bg[phenotype.lower()].eq(1)]
    bg = bg.drop_duplicates("patient_id")
    bg_profs = profiles(ds, bg.isolate_id)
    comparable = [p for p in bg_profs.values() if len(p.shared(reference)) >= PROFILE_MIN_SHARED]
    bg_match = sum(p.matches(reference) for p in comparable)
    n, k = len(profs), len(matching)
    p_value = None
    bg_share = None
    if len(comparable) >= PROFILE_MIN_BACKGROUND:
        bg_share = bg_match / len(comparable)
        p_value = float(binom.sf(k - 1, n, min(max(bg_share, 0.5 / len(comparable)), 1.0)))

    share = k / n
    if (
        share >= PROFILE_SAME_STRAIN_SHARE
        and p_value is not None
        and p_value < PROFILE_SAME_STRAIN_ALPHA
    ):
        verdict = "single_strain"
        text = (
            f"{k} of {n} {organism} cases share one resistance profile ({reference.label}), "
            f"which only {round(100 * bg_share)} % of {phenotype or ''} {organism} isolates "
            "elsewhere had: consistent with a single strain spreading."
        ).replace("  ", " ")
    elif share >= PROFILE_SAME_STRAIN_SHARE:
        verdict = "common_profile"
        text = (
            f"{k} of {n} cases share one profile ({reference.label}), but the profile is common "
            "here, so this says little about a single strain."
        )
    else:
        verdict = "mixed"
        text = (
            f"Only {k} of {n} cases match the most common profile ({reference.label}): "
            "probably several strains or sources, not one."
        )
    return {
        "organism": organism,
        "other_organisms": int(len(iso) - len(cases)),
        "cases": n,
        "matching": k,
        "share": round(share, 3),
        "dominant": {
            "key": reference.key,
            "label": reference.label,
            "tested": sorted(reference.tested),
        },
        "groups": [
            {"key": key, "label": _label(key), "count": c} for key, c in counts.most_common()
        ],
        "case_profiles": {i: p.key for i, p in profs.items()},
        "mean_agreement": round(sum(pairs) / len(pairs), 3) if pairs else None,
        "background": {
            "start": start.date().isoformat(),
            "end": (window_start - timedelta(days=1)).isoformat(),
            "isolates": len(comparable),
            "matching": bg_match,
            "share": None if bg_share is None else round(bg_share, 3),
        },
        "p_value": p_value,
        "verdict": verdict,
        "text": text,
        "method": "Profiles match when resistant/susceptible agree on every agent both isolates "
        f"were tested for (≥ {PROFILE_MIN_SHARED}); intrinsic resistance ignored. Binomial test "
        "of the matching share against the same phenotype × organism in the year before.",
    }


def _label(key: str) -> str:
    return "no acquired R" if key == "-" else f"R: {key.replace(',', ', ')}"
