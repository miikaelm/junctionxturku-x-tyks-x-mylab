"""Pull integration for the doctor's own systems (API-02, API-03), following HL7 CDS Hooks.

The patient record or prescribing system calls a *service* at a defined moment and shows the
short *cards* it returns:
  - `aei-antibiotic-choice` (hook `order-select`): an antibiotic is being ordered → whether
    to avoid it for this infection on this ward (UX-05), alternatives without a warning, active
    alerts on the ward;
  - `aei-patient-context` (hook `patient-view`): a patient record is opened → carrier flags
    and alerts the patient is part of.

Discovery is `GET /api/cds-services`, as the standard prescribes. The context is CDS Hooks
shaped but simplified for the demo: plain fields (ward, infection, sex, age, antibiotic) next to
the standard `patientId` and an optional FHIR `draftOrders` bundle. `as_of` (query) keeps replay
consistent (LIVE-01). Cards cite the statistics engine's own numbers only.
"""

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.alerts import engine
from app.alerts.anomalies import recent_rises
from app.alerts.triage import get_triage_store
from app.api.routes import AsOf, resolve_as_of
from app.data.dataset import get_dataset
from app.data.scope import Scope
from app.patients.registry import patient_record
from app.stats.avoid import avoid, with_recent_rises
from app.stats.therapy import therapy

router = APIRouter(prefix="/api/cds-services", tags=["CDS Hooks"])

SERVICES = [
    {
        "hook": "order-select",
        "id": "aei-antibiotic-choice",
        "title": "AEI: local resistance for an antibiotic order",
        "description": "When an antibiotic is chosen: whether there is a local reason not to "
        "use it for this infection on this ward (resistance at or above 20 %, since when), "
        "alternatives without a warning and active alerts on the ward.",
        "prefetch": {},
    },
    {
        "hook": "patient-view",
        "id": "aei-patient-context",
        "title": "AEI: carrier status and alerts for a patient",
        "description": "When a record is opened: known MRSA / ESBL / VRE / CPE carriage from lab "
        "results, and alerts the patient is part of.",
        "prefetch": {},
    },
]

SOURCE = {"label": "AEI · Tyks Laboratories (decision support)", "url": config.UI_BASE_URL}
CRITICAL_PHENOTYPES = {"CPE", "VRE"}


class CdsRequest(BaseModel):
    hook: str
    hookInstance: str | None = None
    context: dict = Field(default_factory=dict)
    prefetch: dict | None = None


@router.get("")
def discovery() -> dict:
    return {"services": SERVICES}


@router.post("/{service_id}")
def call_service(service_id: str, req: CdsRequest, as_of: date | None = AsOf) -> dict:
    as_of = resolve_as_of(as_of)
    if service_id == "aei-antibiotic-choice":
        return {"cards": order_select(req.context, as_of)}
    if service_id == "aei-patient-context":
        pid = req.context.get("patientId")
        if not pid:
            raise HTTPException(422, "context.patientId is required")
        return {"cards": patient_view(pid, as_of)}
    raise HTTPException(404, f"no CDS service {service_id}")


def card(summary: str, indicator: str, detail: str = "", links: list[dict] | None = None) -> dict:
    return {
        "uuid": str(uuid.uuid4()),
        "summary": summary[:140],
        "indicator": indicator,
        "detail": detail,
        "source": SOURCE,
        "links": links or [],
    }


def link(label: str, path: str) -> dict:
    return {"label": label, "url": f"{config.UI_BASE_URL}/#/{path}", "type": "absolute"}


# ---------- patient-view (API-03) ----------


def patient_view(patient_id: str, as_of: date) -> list[dict]:
    ds = get_dataset()
    record = patient_record(ds, patient_id, as_of)
    if record is None:
        return []
    cards = [carrier_card(f) for f in record["flags"]]
    for a in engine.alerts_for_patient(ds, as_of, get_triage_store(), patient_id):
        if a["type"] == "carrier" or a["triage"]["status"] == "dismissed":
            continue  # the carrier card above says it
        cards.append(
            card(
                f"Part of an active alert: {a['type_label']} on {', '.join(a['wards'])}",
                "critical" if a["severity"] == "critical" else "warning",
                f"{a['title']} (first seen {a['first_seen']}). Infection control has been alerted.",
                [link("Open the alert in AEI", f"alerts/{a['id']}")],
            )
        )
    return cards


def carrier_card(f: dict) -> dict:
    critical = f["phenotype"] in CRITICAL_PHENOTYPES
    month = f["first_positive"][:7]
    organisms = ", ".join(f["organisms"])
    detail = (
        f"First positive {f['first_positive']} on {f['first_ward']} ({organisms}); "
        f"{f['positives']} positive result{'s' if f['positives'] > 1 else ''}, last "
        f"{f['last_positive']} on {f['last_ward']}. Derived automatically from lab results "
        "(AEI carrier registry). Follow the local guideline on contact precautions"
        + (" and screening of contacts." if critical else ".")
    )
    return card(
        f"Known {f['phenotype']} carrier (positive {month}, {f['first_ward']}). "
        "Use contact precautions.",
        "critical" if critical else "warning",
        detail,
        [link("Patient in AEI", f"patients/{f['patient_id']}")],
    )


# ---------- order-select (API-02) ----------


def _antibiotic(context: dict) -> str | None:
    """The chosen agent: context.antibiotic (code or name), or a FHIR draft order's coding."""
    abx = get_dataset().antibiotics
    names = {a.lower(): c for a, c in zip(abx.antibiotic, abx.antibiotic_code)}
    codes = set(abx.antibiotic_code)
    candidates = [context.get("antibiotic")]
    for entry in (context.get("draftOrders") or {}).get("entry", []):
        concept = entry.get("resource", {}).get("medicationCodeableConcept", {})
        candidates.append(concept.get("text"))
        candidates += [c.get("code") for c in concept.get("coding", [])]
        candidates += [c.get("display") for c in concept.get("coding", [])]
    for c in candidates:
        if not c:
            continue
        if c.upper() in codes:
            return c.upper()
        if c.lower() in names:
            return names[c.lower()]
    return None


def _age_band(age) -> str | None:
    if age is None:
        return None
    for label, lo, hi in config.AGE_BANDS:
        if lo <= int(age) <= hi:
            return label
    return None


def _groups_text(groups: list[dict], lead: str) -> str:
    """Subgroup exceptions (UX-10) as card lines."""
    return "".join(
        f"\n\n{lead} {g['label'].lower()}: {g['organism']} {g['pct']:g} % resistant "
        f"({g['r']}/{g['n']}), against {g['rest']['pct']:g} % in {g['rest_label'].lower()}."
        for g in groups
    )


def order_select(context: dict, as_of: date) -> list[dict]:
    ds = get_dataset()
    pid = context.get("patientId")
    record = patient_record(ds, pid, as_of) if pid else None
    ward = context.get("ward") or (record["last_ward"] if record else None)
    if ward not in set(ds.wards.ward_code):
        return [
            card(
                "AEI needs the ward to show local resistance",
                "info",
                "Pass context.ward (e.g. URO) or a patientId with an earlier sample.",
            )
        ]
    infection = context.get("infection") or {
        spec["specimen"]: key for key, spec in config.THERAPY_INFECTIONS.items()
    }.get(context.get("specimen"), "uti")
    if infection not in config.THERAPY_INFECTIONS:
        raise HTTPException(422, f"unknown infection type: {infection}")
    sex = context.get("sex") or (record["sex"] if record else None)
    age = context.get("age") if context.get("age") is not None else (record or {}).get("age")
    ha = context.get("hospitalAcquired")
    scope = Scope(ward, sex=sex, age_band=_age_band(age), hospital_acquired=ha)
    result = therapy(ds, scope, infection, as_of)

    chosen = _antibiotic(context)
    flags = avoid(ds, scope, infection, as_of)
    rises = recent_rises(ds, as_of, get_triage_store(), {ward}, flags["specimen"])
    flags = with_recent_rises(flags, rises)
    cards = []
    where = result["used"]["label"]
    basis = (
        f"Based on {result['isolates']} first isolates ({result['specimen']}), "
        f"{result['window']['start']} – {result['window']['end']}, {where}"
        + (" (too few on the ward itself)" if result["used"]["fell_back"] else "")
        + "."
    )
    label = result["infection_label"].lower()
    flagged = {x["code"]: x for x in flags["avoid"]}
    unsuited = {x["code"]: x for x in flags["not_suited"]}
    risen = {x["code"]: x for x in flags["recent_rise"]}
    some = {x["code"]: x for x in flags["some_patients"]}
    items = {x["code"]: x for x in result["ranked"] + result["unranked"]}
    names = ds.antibiotics.set_index("antibiotic_code").antibiotic

    if chosen in flagged:
        x = flagged[chosen]
        above = [o for o in x["organisms"] if o["status"] == "above"]
        cards.append(
            card(
                f"Avoid {x['name']} for a {label} on {ward}: "
                + "; ".join(f"{o['organism']} {o['pct']:g} % resistant" for o in above),
                "critical" if x["affected_share"] >= 0.5 else "warning",
                "| Organism | Share of infections | Resistant | Above 20 % since | Trend |\n"
                "|---|---|---|---|---|\n"
                + "\n".join(
                    f"| {o['organism']} | {round(100 * o['share'])} % | {o['pct']:g} % "
                    f"({o['r']}/{o['n']}{', ' + o['level_label'] if o['fell_back'] else ''}) | "
                    f"{'at least ' if o['since']['at_least'] else ''}{o['since']['date']} | "
                    f"{o['direction'] or '–'} |"
                    for o in above
                )
                + _groups_text(x["subgroups"], "Under the limit for")
                + f"\n\n{flags['method']} Decision support, not a prescription.",
                [link("Open My Ward in AEI", "ward")],
            )
        )
    elif chosen in risen:
        x, r = risen[chosen], risen[chosen]["rise"]
        cards.append(
            card(
                f"{x['name'].capitalize()}: resistance has risen on {ward} in the last 4 weeks",
                "warning",
                f"{r['organism']} ({flags['specimen']}): {r['observed']['pct']:g} % resistant "
                f"({r['observed']['r']}/{r['observed']['n']}) from {r['window']['start']} to "
                f"{r['window']['end']}, against {r['expected']['pct']:g} % in the 12 months before. "
                f"Alert raised {r['since']}. "
                + (
                    f"Likely cause: {r['cause']['type_label'].lower()} ({r['cause']['title']}); "
                    f"{r['cause']['matching']} of the {r['cause']['of']} resistant isolates are "
                    "its cases. "
                    if r["cause"]
                    else ""
                )
                + f"The 12-month figure is still below {flags['threshold_pct']:g} %, so this is "
                "a recent change. Decision support, not a prescription.",
                [link("Open the alert in AEI", f"alerts/{r['alert_id']}")]
                + (
                    [link("Open the outbreak in AEI", f"alerts/{r['cause']['alert_id']}")]
                    if r["cause"]
                    else []
                ),
            )
        )
    elif chosen in unsuited:
        x = unsuited[chosen]
        intrinsic = [o["organism"] for o in x["organisms"] if o["status"] == "intrinsic"]
        cards.append(
            card(
                f"{x['name'].capitalize()} does not act on most {label} organisms",
                "warning",
                f"Intrinsically resistant: {', '.join(intrinsic)}.",
            )
        )
    elif chosen in some:
        x = some[chosen]
        groups = ", ".join(g["label"].lower() for g in x["subgroups"])
        cards.append(
            card(
                f"{x['name'].capitalize()} on {ward}: no warning overall, but high in {groups}",
                "warning",
                f"Over all {label}s here no main organism is {flags['threshold_pct']:g} % or more "
                "resistant, but for some patients it is."
                + _groups_text(x["subgroups"], "Over the limit for")
                + "\n\nPass the patient's sex, age and onset (or a patientId) to check their group. "
                "Decision support, not a prescription.",
                [link("Open My Ward in AEI", "ward")],
            )
        )
    elif chosen and chosen in items:
        x = items[chosen]
        rows = "\n".join(
            f"| {p['organism']} | {round(100 * p['share'])} % | "
            + (
                "intrinsically resistant"
                if p["status"] == "intrinsic"
                else "not tested"
                if p["status"] == "not_tested"
                else f"{p['susceptible_pct']} % susceptible ({p['n']} tested)"
            )
            + " |"
            for p in x["organisms"]
        )
        cards.append(
            card(
                f"No local resistance warning for {x['name']} ({label}, {ward})",
                "info",
                f"No main organism is {flags['threshold_pct']:g} % or more resistant. Estimated "
                f"coverage ~{round(x['coverage_pct'])} % (95 % interval {x['ci_low']}–"
                f"{x['ci_high']} %). {basis}\n\n"
                f"| Likely organism | Share | {x['name'].capitalize()} |\n|---|---|---|\n{rows}\n\n"
                "Untested organisms count as not covered. Decision support, not a prescription.",
                [link("Open My Ward in AEI", "ward")],
            )
        )
    elif chosen:
        cards.append(
            card(
                f"No local data on {names[chosen]} for {label}s",
                "info",
                f"{names[chosen].capitalize()} is not reported for {result['specimen']} cultures. "
                f"{basis}",
            )
        )

    if chosen is None and flagged:
        cards.append(
            card(
                f"Avoid for a {label} on {ward}: " + ", ".join(x["name"] for x in flagged.values()),
                "warning",
                flags["method"],
                [link("Open My Ward in AEI", "ward")],
            )
        )
    if chosen in flagged or chosen in unsuited or chosen in risen:
        clear = {x["code"] for x in flags["no_warning"]}
        best = [b for b in result["ranked"] if b["code"] in clear][:3]
        if best:
            cards.append(
                card(
                    "Without a local warning: "
                    + ", ".join(
                        f"{b['name']} (~{round(b['coverage_pct'])} %"
                        + (", reserve" if b["reserve"] else "")
                        + ")"
                        for b in best
                    ),
                    "info",
                    f"Ranked by estimated coverage of {label}s. {basis} Choose by the local "
                    "guideline: reserve agents such as meropenem are kept for resistant infections.",
                    [link("Therapy helper in AEI", "ward")],
                )
            )

    alerts = [
        a
        for a in engine.alerts_at(ds, as_of, get_triage_store(), wards={ward})
        if not a["routine"] and a["triage"]["status"] != "dismissed"
    ]
    for a in alerts[:3]:
        cards.append(
            card(
                f"Active on {ward}: {a['type_label'].lower()}, {a['title']}",
                "critical" if a["severity"] == "critical" else "warning",
                f"First seen {a['first_seen']}. {a['evidence'].get('method', '')}",
                [link("Open the alert in AEI", f"alerts/{a['id']}")],
            )
        )
    if record:
        cards += [carrier_card(f) for f in record["flags"]]
    return cards
