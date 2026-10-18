# AEI – Antibiotic Efficacy Indicator

A continuously updated antimicrobial-resistance surveillance tool, built for the Tyks Laboratories ×
Mylab challenge at JunctionX Turku by **First Isolate** (Miikael Mändmets).

**Live demo:** https://memand-aei.hf.space (hosted for the judging; may be taken down afterwards)

**Demo video (2 min):** https://youtu.be/iAPOzSQRnzA

Today, Tyks compiles resistance reports once a year, for the whole hospital. A doctor choosing an
antibiotic needs to know what works on their own ward right now. Finding the resistance patterns is
the easy part; the hard part is getting the answer to busy people at the moment they decide. AEI is
built around three of them:

| User | Question | What AEI gives them |
|---|---|---|
| Clinician | "What should I not use here, and what instead?" | My Ward opens on what to avoid on the ward right now, new rises first, with the reason in words. Inside the patient record, the antibiotic order is checked against the patient's own results and the ward's last 4 weeks, with alternatives (narrow-spectrum first) and one-click switching. |
| Infection control | "Is something spreading?" | Only what is abnormal, from the county (Varha) to the hospital to the ward. Each alert says why it fired and whether the cases share one resistance profile. Triage decides what clinicians are warned about. |
| Stewardship | "What is slowly getting worse?" | Long-term trends and threshold crossings (e.g. trimethoprim past the 20 % limit for empirical use), compared with the Finnish national figure, each with an owner and a review status. |

Everything runs on the organisers' full synthetic dataset (about 47,000 cultures over three years).

## Running it

Needs Python 3.11+ with [uv](https://docs.astral.sh/uv/), and Node.js.

```bash
# Backend: http://localhost:8000 (API docs at /docs)
cd backend
uv sync
uv run uvicorn app.main:app --reload

# Frontend: http://localhost:5173 (proxies /api to the backend)
cd frontend
npm install
npm run dev
```

On startup the backend warms its caches for the demo dates (2–3 minutes; the console prints
`AEI warm-up done`). Pages work before that, only slower.

Tests: `cd backend && uv run pytest`.

**Using the demo:** pick a role on the start page. The bar at the bottom ("Demo only") moves the
date, replays the data day by day, jumps to any past alert, and opens the mock patient record.
[docs/DEMO.md](docs/DEMO.md) lists the demo dates and patients and what each step should show.

## How it works

### Numbers you can trust

- **First isolate** per patient × organism × specimen in each period, as the challenge brief asks.
- A percentage is shown only from **30 isolates**; below that the counts are shown (e.g. 7/11).
- **95 % Wilson intervals** on every percentage.
- **Fallback to a wider level** when a ward has too few isolates (ward → all hospital wards or all
  health centres → all), always labelled.
- The **last 4 weeks next to the last 12 months**, plus calendar years and custom periods in Explore.
- **Intrinsic resistance** (EUCAST expected phenotypes) is shown as such, never as an alert.
  Urine-only agents are reported only for urine.
- Known splits on by default (e.g. urine E. coli by sex), and **subgroup discovery** tests every
  patient dimension for resistance differences.
- **National reference:** THL Finres 2023 figures as a comparison line, never used for alerts.

### Detection (general methods; nothing is hardcoded to the dataset's events)

| Detector | Method |
|---|---|
| Outbreak / cluster | Poisson test of new phenotype cases (MRSA, ESBL, …) against the ward's own baseline, Benjamini–Hochberg FDR across all ward × phenotype pairs |
| Same strain? | Resistance-profile similarity of the cluster's cases, binomial test against the year before |
| Sudden resistance shift | One-sided Fisher test, last 4 weeks vs the previous 12 months, FDR-corrected |
| Slow drift | Cochran–Armitage trend test over quarters, FDR-corrected, plus crossings of the 20 % limit |
| Novelty | A phenotype or rare organism not seen on a ward for a long time, or ever |
| Sentinel | Any CPE, VRE, carbapenem or vancomycin resistance: one case is one alert |
| Multi-ward | The same phenotype and resistance profile on two or more wards within a window |
| Data gap | Sample volume far below expected, so "no data" is never shown as "no resistance" |
| Carriers | MRSA / ESBL / VRE / CPE carriers flagged automatically, with an alert when one reappears on another ward |

On the organisers' data, AEI finds the Urology ESBL outbreak (June 2025) 3 days after it began, the
ICU MRSA cluster (March 2026) on its first case, the health-centre data gap on its second silent day,
the trimethoprim drift as the only significant trend among 527 series, and every CPE and VRE case on
its sample day.

### Integration

- **REST API** for everything the screens show (`/api`, documented at `/docs`).
- **CDS Hooks** services (`GET /api/cds-services`) for the hooks `patient-view` (carrier flags and
  active alerts), `order-select` (local resistance, alternatives) and `order-sign` (warnings again,
  override reasons, "change to" suggestions), plus the feedback endpoint.
- **Push webhooks** for new alerts and carrier flags.
- A **mock patient record** inside the app (demo bar → "Open EHR demo") calls these services the way
  a real record system would.

## Limitations

- The data is fully synthetic, and "live" updating is shown by replaying it (Live Replay); there is
  no connection to a real lab feed yet. Ingestion is built to be incremental.
- The patient record is a mock. The CDS Hooks services follow the standard's structure, but the
  request context is simplified (plain ward / infection / patient fields next to the standard
  `patientId`), there is no FHIR prefetch or authentication, and they have not been tested against
  a real record system.
- Triage and stewardship reviews are stored in local JSON files (`backend/.state/`); CDS feedback is
  kept in memory. There are no user accounts.
- The spread view is work in progress: the dataset has no admission or transfer data, so it shows
  where cases were sampled, not how patients moved.
- Conventions taken as assumptions and not yet confirmed with Tyks: hospital-acquired = sampled on
  day 3 or later of the admission; 20 % resistance as the limit for empirical use.
- The tool has not yet been tested with clinicians, infection control or stewardship users.

## Repository layout

```
backend/    FastAPI app (app/: data, stats, detectors, alerts, patients, api) and tests
frontend/   React + TypeScript + Vite app (src/views, src/components, src/api)
docs/       DATA_NOTES.md (dataset facts), DEMO.md (demo dates and patients)
synthetic_microbiology_dataset/   the challenge data (CSV) and its README
PROJECT.md  requirements, decisions and the validation answer key
```
