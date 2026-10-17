# AEI – Antibiotic Efficacy Indicator · Project Document

JunctionX Turku hackathon · Case partners: **Tyks Laboratories × Mylab**

This is the single source of truth for the project. Every session (human or AI) should
read it first and update the checkboxes / decisions as work progresses.

**Legend**
- Priority: **M** = must have · **S** = should have · **C** = could have (stretch)
- Status: `[ ]` not started · `[~]` in progress · `[x]` done
- ❓ = concept the team has flagged as not yet fully understood → explained in §11
- *(proposed)* = added 2026-10-17 from mentor discussion; priority not yet confirmed by the team

---

## 1. The challenge in one paragraph

Tyks Laboratories currently compiles antimicrobial resistance (AMR) reports **once a year,
at hospital level**. That is too slow and too coarse: a doctor choosing an antibiotic wants
to know how bacteria **on their own ward** are behaving **right now**. Build a
**continuously updated** tool that shows **the previous 4 weeks and the annual picture**,
filterable by dataset parameters.

> **Insight from the organizers:** "This is not a basic BI dashboard task … that's too easy and
> won't create real value. The hard part is making a continuously updated tool which is highly
> usable and versatile for the end-user. An AI-native approach is one possible angle."

**Judging (25 % each)**
1. Demonstrated understanding of the challenge
2. Suitability to the challenge description and the insight
3. Usability
4. **Ability to detect deviations and anomalies in the data**

**Prizes:** 1400 € / 350 € / 250 € + internship/thesis possibilities at Mylab.

### Data at a glance (`synthetic_microbiology_dataset/`)
- 10,000 patients · 46,792 cultures · 24,571 isolates · 172,381 S/R results
- Period **2023-10-02 → 2026-09-27** (156 weeks). The scenario's "today" is **2026-09-27**.
- Chain: `patients` → `cultures` (sample) → `isolates` (organism) → `susceptibility` (S/R).
  Keys: `patient_id`, `culture_id`, `isolate_id`.
- 9 wards: ED, MED-A, MED-B, SURG, URO, ICU, GER (hospital) + PHC-N, PHC-S (health centres).
  No pediatric ward, but 2,525 cultures are from patients < 18 years, spread across wards.
- Specimens: urine (70 %), wound, blood. 9 organisms, 13 antibiotics, phenotype flags
  ESBL / MRSA / VRE / CPE.
- **Dates only, no timestamps** → day is the finest time resolution.
- Patients move between wards: 73 % of patients appear on ≥ 2 wards. There are no transfer /
  admission-discharge records, only `admission_date` on inpatient samples.
- Data is clean (no orphans, duplicates or inconsistencies). Finnish + English names available.
- External EARS-Net / THL data: **optional**, reference only (see DATA-08).

### Context: Varha (design decided 2026-10-17, see UX-01 and §9)
The mentor framed things from the **Varha** angle (*Varsinais-Suomen hyvinvointialue*, the
wellbeing services county of Southwest Finland). Since 2023 it has run public health, social
and rescue services for ~490,000 residents in 27 municipalities: Tyks, regional hospitals
(e.g. Loimaa, Vakka-Suomi), health centres, elderly care and home care. Our dataset is a
**miniature** of this: one hospital with 7 wards, 2 health centres and 5 home areas. It is not
Varha-wide. The mentor's "grandma" path (Loimaa → Tyks → care home) stays inside Varha, so all
of its samples can reach the same lab.

---

## 2. Guiding principles (apply to every feature)

1. **Statistically honest numbers.** Never show a bare percentage that small numbers can't
   support. Follow surveillance rules (first isolate, n ≥ 30) and make uncertainty visible.
2. **Automatic alerts.** The tool tells the user when something changes; users don't hunt
   through charts.
3. **Fit the clinician's workflow.** A doctor answers "what works on my ward for this
   infection?" in seconds, with no analytics skills needed, ideally inside the systems they
   already use (see API).
4. **General methods, never hardcoded.** Detection must find events by itself using general
   statistical methods. The planted events (§8) are an **answer key for validation only**.
5. **Not a BI dashboard.** Charts and filters are table stakes. The value is in domain
   logic, alerts, role-specific views and continuous updating.

---

## 3. Users, use cases and views

Three primary roles (keep it to ~3; confirm with the mentor, see §10.1).

| # | Role | Who | Main question | How often | Home view |
|---|---|---|---|---|---|
| R1 | **Clinician** | Ward / on-call doctor; also health-centre GPs (same needs, urine-first) | "My patient has an infection. Which antibiotic is likely to work on my ward right now?" | Daily, seconds, under time pressure | V1 |
| R2 | **Infection control** | Infection-control nurse / hygienist, infection physician | "Is something spreading? Which wards, which patients?" | Daily morning check + on alert | V3 |
| R3 | **Lab & stewardship** | Clinical microbiologist (Tyks lab). Secondary uses: long-term trends / guideline review (stewardship), annual reporting | "Are alerts real? Is data arriving? What are the long-term trends? What do I report?" | Daily–quarterly | V7 / V6 |

### Views

| ID | View | For | Purpose |
|---|---|---|---|
| V1 | **My Ward** (landing page for R1) | R1 | Organism × antibiotic table for the selected ward and specimen. **Last 4 weeks next to last 12 months.** Traffic-light colouring, counts, uncertainty, "insufficient data" state. Ward remembered between visits. Contains: the **therapy-helper mode** (V2), an **alert strip for this ward** (from V3), and a **data-freshness badge** (from V7). Visual quality is a priority here. |
| V2 | **Therapy-helper mode** (inside V1, not a separate page) | R1 | Pick infection type (UTI / bloodstream / wound) + patient context (sex, age, hospital-acquired?) → a ranked "best choices" strip above the table, by probability of covering the likely organisms. Same logic powers the AI assistant (AI-01) and the API (API-02). Decision support, not a prescription. |
| V3 | **Alert inbox** (home for R2) | R2, R3 | All active alerts with type, severity, ward, first-seen date and triage status (new / investigating / confirmed / dismissed). R1 sees only their ward's alerts, as the strip in V1. |
| V4 | **Alert detail / outbreak investigation** | R2, R3 | Case timeline, line list of cases (date, ward, specimen, days since admission), resistance-profile similarity between cases, and why the alert fired (baseline vs observed). |
| V5 | **Ward × time overview** | R2 | Heatmap of wards × weeks for phenotype counts (MRSA/ESBL/CPE/VRE) and key resistance rates. Shows at a glance where and when things changed. |
| V6 | **Trend explorer & reports** (separate "not daily" workflow) | R3 | Long-term trends by organism–antibiotic, with guideline thresholds (e.g. 20 % line), period comparisons (year vs year), and annual-report export. |
| V7 | **Data quality / feed status** | R3 | Sample volume per ward per day vs expected, gaps, last-received dates. Freshness also appears as a badge on every other view (VIEW-12). |
| V8 | **Time cursor / replay control** (global header) | All, demo | Sets the "as-of" date. Every view and alert recomputes as if it were that day. |
| V9 | **AI assistant panel** | All | Natural-language questions and plain-language alert explanations. |
| V10 | **Spread / footprint view** | R2 | For a chosen organism, phenotype or resistance profile: where it appears across wards over time, which wards share the same profile, and where the patients from a cluster went afterwards (PAT-03). |
| V11 | **Mock patient-record (EHR) page** (demo) | Demo | A fake "doctor's main system" screen that calls our API and shows the returned cards (API-05). |

---

## 4. Functional requirements

### 4.1 Data layer (DATA)
- [x] **DATA-01 (M)** Load and join all CSVs (cultures ↔ patients ↔ isolates ↔ susceptibility, plus code tables).
- [x] **DATA-02 (M)** ❓ **First-isolate rule:** count only the first isolate per patient × organism × specimen type per analysis period. Apply this in every resistance-% calculation. (Explained in §11.)
- [x] **DATA-03 (M)** **Hospital-acquired flag:** inpatient sample taken on day ≥ 3 after `admission_date`, i.e. `sample_date − admission_date ≥ 2` days, with the admission day counted as day 1. Convention to be confirmed (§10.1).
- [~] **DATA-04 (M)** **Time windows** relative to the as-of date: rolling last 4 weeks, rolling last 12 months, calendar year, and an arbitrary custom range.
- [x] **DATA-05 (M)** **Incremental ingestion:** new rows can be appended and only affected aggregates recomputed. Architected like a live feed from the lab information system (Mylab).
- [x] **DATA-06 (M)** Respect reporting rules: urine-only antibiotics (MEC, TMP, NIT) only for urine specimens.
- [x] **DATA-07 (M)** **Intrinsic resistance table** (EUCAST Expected Resistant Phenotypes), e.g. Klebsiella–ampicillin, Proteus–nitrofurantoin. Show these as "intrinsically resistant", never as alerts or as "100 % resistance" findings.
- [ ] **DATA-08 (C)** Optional national reference values (THL Finres) as a "Finland level" comparison line.

### 4.2 Statistical honesty (STAT)
- [x] **STAT-01 (M)** Minimum-sample rule: a resistance % is shown as a headline number only when n ≥ 30 first isolates. Below that the cell shows an explicit "insufficient data" state, plus counts.
- [x] **STAT-02 (M)** ❓ **Confidence intervals:** every % comes with a 95 % interval (e.g. Wilson), displayed visually (range bar / tooltip).
- [x] **STAT-03 (M)** ❓ **Show counts, not just %:** e.g. "7 / 11 resistant" alongside or instead of a percentage when n is small.
- [x] **STAT-04 (M)** ❓ **Automatic fallback to a broader group:** when ward-level data is too thin, fall back along a hierarchy (ward → hospital or primary care → all), and **clearly label** which level is shown.
- [x] **STAT-05 (S)** ❓ **Fallback to the annual figure:** when the 4-week number is unreliable, show the 12-month number as the main value and the 4-week one as a secondary signal.
- [ ] **STAT-06 (S)** ❓ **Shrinkage (smoothing) estimate:** blend a small ward-level number toward the broader-group number, weighted by sample size. Gives a single, more stable "best estimate". Check with the mentor (§10.1).
- [x] **STAT-07 (M)** **Stratification:** all dimensions are available as filters (dynamic). Clinically known splits are **on by default**: urine E. coli by **sex** (men have ~2× ciprofloxacin resistance), in/outpatient, hospital-acquired vs community.
- [x] **STAT-08 (S)** Multiple-testing awareness in alerting: control false alarms when testing many ward × organism × antibiotic combinations (e.g. false-discovery-rate correction, minimum-n gates).
- [x] **STAT-09 (M)** **Automatic subgroup-difference discovery (important):** test each dimension (sex, age band, home area, ward type, hospital-acquired, …) for significant resistance differences and surface "resistance differs notably by X". The general-method counterpart of STAT-07's defaults: it should rediscover the known sex effect by itself. Uses STAT-08 to keep false discoveries down.

### 4.3 Anomaly detection (ANOM): four core anomaly types + novelty
All detectors run automatically on every update (or as-of change) with general methods and configurable thresholds.

- [x] **ANOM-01 (M) Outbreak / cluster of resistant cases.** Counts of a phenotype (MRSA, ESBL, …) per ward per week rise above that ward's expected baseline. Methods: Poisson/negative-binomial baseline, CUSUM, or CDC EARS C1–C3 / Farrington-style. Prioritise hospital-acquired cases.
- [x] **ANOM-02 (M) Sudden resistance-rate shift.** The resistance % for an organism–antibiotic pair on a ward (last 4 weeks) differs significantly from its baseline (previous 12 months). Methods: binomial / Fisher exact test, CUSUM on proportions, minimum-n gate.
- [x] **ANOM-03 (M) Slow drift / long-term trend.** Gradual increase over months or years. Methods: logistic regression on time, Mann-Kendall or Cochran-Armitage trend test. Also flags **threshold crossings** (e.g. empirical agent passing the commonly used **20 % resistance** limit). This is the stewardship workflow (V6), not a daily alert.
- [x] **ANOM-04 (M) Data-quality gap.** Sample volume per ward per day/week far below expected, or zero for several days. Distinguish "no resistance" from "no data". Shown in V7 and as the freshness badge / warning on affected views.
- [x] **ANOM-05 (S)** Cluster evidence: similarity of resistance profiles between cases in a cluster (same antibiogram pattern → likely same strain).
- [x] **ANOM-06 (S)** Each alert records **why** it fired (observed vs expected, method, p-value or score) for display in V4 and for the AI explanation.
- [x] **ANOM-07 (S)** Measure **detection latency** on replay: days from event start to first alert.
- [x] **ANOM-08 (S)** **Novelty alert ("not seen here for a long time / ever"):** a phenotype (MRSA/ESBL/VRE/CPE) or rare organism appears on a ward where it hasn't been seen for a configurable period, or never before. The mentor's example was "not seen in 20 years"; our data covers only 3 years, so the longest possible lookback is "first since records began". Fires on the *first* case, before outbreak statistics can. Skip common organisms to avoid noise.
- [x] **ANOM-09 (S)** **Multi-ward signal:** the same phenotype with a similar resistance profile appears on ≥ 2 wards within a configurable window. Flags possible spread for infection control without claiming direction ("seen on URO and GER"), and feeds V10.

### 4.4 Notifications & sentinel events (NOTIF)
- [x] **NOTIF-01 (M)** **Rare sentinel events trigger immediately**, without statistics: any CPE, any VRE, any carbapenem (meropenem) resistance, any vancomycin resistance. One case = one alert.
- [x] **NOTIF-02 (M)** In-app alert badge and inbox (V3), plus the alert strip on the affected ward's V1 page.
- [x] **NOTIF-03 (S)** Subscriptions by role and ward (e.g. infection control gets all wards; a ward doctor gets their own ward). Whether ward doctors should also see other wards' alerts: ask the mentor (§10.1).
- [x] **NOTIF-04 (S)** Severity levels (e.g. sentinel = critical, outbreak = high, carrier re-appearance = high, rate shift = medium, novelty = medium, trend = info / periodic digest).
- [x] **NOTIF-05 (S)** **Simulated external delivery** (email / push / Teams message / webhook to other systems, see API-04) and a weekly or monthly digest for trend findings. Important for the "fits existing workflow" story.
- [x] **NOTIF-06 (S)** Alert triage workflow: new → investigating → confirmed / dismissed, with dismissed alerts suppressing duplicates.

### 4.5 Views & usability (VIEW)
- [~] **VIEW-01 (M)** V1 My Ward, as described in §3, with 4-week and 12-month side by side. **Visual quality is a priority.**
- [~] **VIEW-02 (M)** Filters on dataset parameters: ward, ward type (in/out), institution, specimen, organism, antibiotic, sex, age band, hospital-acquired, period.
- [x] **VIEW-03 (M)** V3 Alert inbox and V4 Alert detail.
- [x] **VIEW-04 (S)** V2 Therapy-helper mode inside V1 (❓ see "weighted syndromic antibiogram" in §11).
- [x] **VIEW-05 (S)** V5 Ward × time heatmap.
- [x] **VIEW-06 (M)** V6 Trend explorer, with threshold lines and year-vs-year comparison.
- [x] **VIEW-07 (M)** V7 Data quality / feed status.
- [x] **VIEW-08 (S)** Role-based entry: choose one of the 3 roles → land on that role's home view.
- [~] **VIEW-09 (S)** Clinician-first UX: core answer reachable in ≤ 2 clicks, readable on a tablet or phone, plain-language labels, consistent colour meaning (green = likely effective, red = high resistance, grey = insufficient data).
- [ ] **VIEW-10 (C)** Finnish / English language toggle (the data already contains Finnish names). Optional.
- [ ] **VIEW-11 (C)** Export: annual report (PDF/CSV).
- [~] **VIEW-12 (M)** **Data-freshness badge on every view** (e.g. "PHC-S: last sample 7 days ago ⚠") so "no data" is never mistaken for "no resistance".

### 4.6 Continuous updating & replay (LIVE)
- [x] **LIVE-01 (M)** **Global as-of date (time cursor):** every view and every detector computes as if "today" were that date, using only data up to it.
- [x] **LIVE-02 (M)** **Replay mode:** play data forward day by day (adjustable speed); views and alerts update live, with animated transitions; alerts appear at the moment they would have fired.
- [ ] **LIVE-03 (C)** "What's new since last visit" summary for the user. Optional.
- [x] **LIVE-04 (S)** Jump-to-event shortcuts for the demo (start replay just before each validation event in §8).

### 4.7 AI layer (AI): optional angle, via OpenRouter
- [ ] **AI-01 (S)** Natural-language query, e.g. "80-year-old man, UTI, Geriatrics — what works?" → answered from the tool's computed statistics (V2 logic), with the numbers shown.
- [ ] **AI-02 (S)** Plain-language alert explanations generated from ANOM-06 data ("13 MRSA cases in ICU in 3 weeks vs ~0.3 expected; 10 hospital-acquired; recommend …").
- [ ] **AI-03 (C)** Auto-written periodic summary (weekly ward summary, monthly stewardship digest).
- [ ] **AI-04 (M if AI is used)** Guardrails: the AI only cites numbers the statistics engine computed (no invented figures), shows its sources, and is labelled as decision support.

### 4.8 Non-functional (NF)
- [~] **NF-01 (M)** Views respond in < 2 s on the full dataset.
- [~] **NF-02 (M)** Runs locally for the demo with no internet dependency (except optional AI).
- [~] **NF-03 (S)** Privacy by design: prescriber views show aggregates only; patient-level line lists only in infection-control / lab roles and patient-context API calls. The data is synthetic, but design as if it were real.
- [~] **NF-04 (S)** Detection thresholds are configurable, not magic numbers in code.

### 4.9 Patient-level risk & spread (PAT)
The mentor's "grandma" story: a carrier moves Loimaa hospital → Tyks → nursing home and spreads
the bacteria along the way. The receiving unit should know. Carrier information reaches other
systems mainly through the API (§4.10); how Tyks handles it today is an open question (§10.1).
- [x] **PAT-01 (M)** **Carrier registry:** derived automatically from results; any patient positive for MRSA / ESBL / VRE / CPE gets a carrier flag (organism, phenotype, first positive date, ward). Required by API-03.
- [x] **PAT-02 (S)** **Carrier re-appearance alert (in-tool):** when a known carrier gets a new sample on any ward / institution, notify that ward (contact precautions). Demonstrable on current data: 352 of 491 ESBL carriers and 70 of 110 MRSA carriers later appear on a different ward.
- [x] **PAT-03 (S)** **Spread / footprint view (V10) for infection control:** for a chosen organism, phenotype or resistance profile:
  - timeline with one row per ward and a dot per case, coloured by resistance profile, so the same profile on several wards stands out (ANOM-09);
  - each patient's sample path across wards, drawn as lines between their dots;
  - "where did they go next": for a cluster (e.g. the URO ESBL outbreak), the wards where its patients were sampled afterwards, as a follow-up list for infection control.

  **Caveat:** inferred from sample dates, not real transfer records. The synthetic data does not appear to model transmission or persistent carriage (max 2 MRSA isolates per patient), so show co-occurrence and patient paths but do **not** claim direction ("ICU got it from ED").
- [ ] **PAT-04 (C)** Cross-institution scenario (external hospital → Tyks → nursing home). Needs extension data (EXT-02).

### 4.10 Integration API (API)
The doctor's existing systems (patient record, prescribing) talk to our service in two
directions:
- **Pull:** the other system asks us at the right moment, following the real-world standard
  **HL7 CDS Hooks** (it calls a service at defined moments and gets back short "cards" to display).
- **Push:** we send events, such as "patient X is a flagged carrier" or a new alert, to the other system's endpoint.

The UI itself is a client of the same API.
- [x] **API-01 (M)** REST API exposing the same statistics and alerts the UI uses.
- [x] **API-02 (M)** **Prescribing context (pull,** `order-select` **style):** given ward + infection/specimen type (+ sex, age) and optionally the chosen antibiotic → resistance summary and active alerts as cards. E.g. "Ciprofloxacin: 25 % resistance in URO E. coli, last 4 weeks; active ESBL cluster on this ward."
- [x] **API-03 (M)** **Patient context (pull,** `patient-view` **style):** given a patient id → carrier flags and relevant alerts. E.g. "Known ESBL carrier (positive 2025-06, URO). Use contact precautions."
- [x] **API-04 (M)** **Push / webhooks:** send new alerts and new carrier flags to registered external endpoints, e.g. a mock "Tyks" receiver. Implements NOTIF-05.
- [x] **API-05 (M)** V11 mock patient-record page that calls the API and renders the cards (demo).

### 4.11 Extension data (EXT) *(proposed)*
We may generate our own data and plant our own scenarios on top of the organizers' data to
show more of what the tool can do. This is a hackathon, not a test.
- [ ] **EXT-01 (S)** **Live-feed continuation:** generate data after 2026-09-27 with the same schema, based on observed rates, so "today" really ticks forward in the demo.
- [ ] **EXT-02 (C)** **Patient movement data:** admission/transfer events including an external hospital (e.g. Loimaa), a nursing home, and possibly a pediatric ward, for PAT-04.
- [ ] **EXT-03 (S)** **Our own planted scenarios** (e.g. a cross-institution carrier path, a multi-ward spread, a novelty case on a pediatric ward) to showcase features the organizers' data can't.
- [ ] **EXT-04 (M if any EXT is built)** Practicalities: separate folder (e.g. `extension_data/`), generator script with a fixed seed, identical schema so the tool runs on either dataset. Say in the pitch which scenarios are ours, since the judges know their own data.

### 4.12 Beyond antibiotics: platform angle (FUT): SHELVED 2026-10-17
Parked for now; may come back as a pitch slide. Framing: the engine is general (a stream of lab
results × grouping dimensions × detectors → alerts + API). Antibiotic resistance is the first module.
- [ ] **FUT-01 (C)** **Sample-quality monitoring:** "mixed growth" (contaminated urine sample) rate per ward, about 2 % on ICU vs up to 11 % on GER. Already in the data and cheap to build.
- [ ] **FUT-02 (C)** **Hospital-acquired infection tracking:** hospital-acquired bloodstream infections, surgical wound infections. Partly possible with current data.
- [ ] **FUT-03 (C)** **Regional view** by `home_area`. Already in the data.
- [ ] **FUT-04 (pitch)** **Seasonal epidemic early warning:** flu / RSV / norovirus test positivity, for capacity planning.
- [ ] **FUT-05 (pitch)** **Analyser drift detection** (*patient-based real-time quality control*): a steady shift across many patients' routine chemistry results signals a machine going out of calibration. Highly relevant for Mylab.
- [ ] **FUT-06 (pitch)** **Diagnostic stewardship:** unusual test-ordering patterns.

### 4.13 Usability optimization phase (UX) *(proposed)*
Comes **after** the base features (slices 1–4 are built function-first with simple visuals, see §12).
This phase reworks *how* the data is presented, per role. Decide the approach before building.
- [x] **UX-01 (S)** **Varha angle: figure out first, then build.** How the tool works at the scale of
  the wellbeing services county (§1): which levels exist (Varha area → institution / hospital → ward),
  whether we need extension data (EXT-02) to show more than one hospital, and how the pitch positions
  it (mentor question in §10.1). Output: a design decision in §9 before any code. **Decided, see §9.**
- [ ] **UX-02 (S)** **Exceptions-first view for infection control (R2):** open on what is abnormal
  instead of the full antibiogram. An *anomaly* is an active alert or a feed problem; chronic red cells
  are not anomalies (they go to the ward's "avoid" list, UX-05). Normal data stays reachable one step
  deeper ("show all"), not up front. The anomaly *is* the alert: clicking it opens V4.
- [ ] **UX-03 (S)** **Drill-down hierarchy for big-picture users (R2, R3):** Varha → institution (Tyks,
  PHC-N, PHC-S) → ward. Higher levels show **counts of anomalies, never an overall resistance %**, and
  list only the children that have anomalies, plus one quiet line naming the calm ones ("4 wards calm:
  …"). Clicking a child drills down; same page template at every level. Other Varha hospitals appear as
  greyed placeholders ("not in demo data"). Home area is a separate community lens, not a level.
- [ ] **UX-05 (S)** **Clinician exceptions view (R1):** My Ward opens on what *not* to use and what is
  going on on the ward, nothing else up front. Each "avoid" line: agent, infection, % resistant with n
  (e.g. 40/130), **since when** above the threshold, and direction (rising / stable / easing). Based on
  resistance in the organisms the agent targets, not on WISCA coverage. Ward alerts (clusters etc.) with
  since when and what to do; known carriers sampled as a quiet count. The ranked therapy helper and full
  antibiogram move further down. No badge, no notifications for clinicians.
- [ ] **UX-06 (S)** **Notifications as delivery settings:** alerts are the first-party object in the
  app; notifications are only how people hear about them outside it. The Notifications page moves from
  the main nav to a settings (⚙) entry (subscriptions, channels, delivery log, digest).
- [ ] **UX-04 (S)** **Visual polish pass:** consistent look across all views, animations, responsive
  layouts, role-specific landing pages (with VIEW-08). V1 got an early polish in slice 1.

---

## 5. Domain rules reference

| Rule | Detail |
|---|---|
| First isolate | First isolate per patient × species × specimen type per period (THL Finres, WHO GLASS, CLSI M39). |
| Minimum n | Report % only with ≥ 30 isolates. |
| Hospital-acquired | Sample taken on hospital day 3 or later (`admission_date`). |
| Urine-only agents | Mecillinam, trimethoprim, nitrofurantoin are reported only for urine. |
| Intrinsic resistance | Per EUCAST Expected Resistant Phenotypes v1.2, e.g. Klebsiella–AMP, Proteus–NIT. These are not "findings". |
| Sex difference | Urine E. coli resistance differs by sex (men higher, especially CIP). |
| Only S/R | No "I" category, MIC or zone diameters in this data. |
| Guideline column (optional) | EUCAST version changes every January. In real life breakpoint changes can cause artificial jumps; no such artifact is visible in this data. Annotating it on trend charts is optional. |
| Empirical-use threshold | ~20 % resistance is a commonly used upper limit for choosing an empirical agent for cystitis (e.g. IDSA for TMP-SMX). Verify the local/Finnish convention (§10.1). |

---

## 6. Demo storyline (draft)
1. Problem: annual hospital-level report vs. what a doctor needs.
2. Doctor on Geriatrics opens **My Ward** → instant answer, honest uncertainty, freshness badge.
3. **Replay** through June 2025 → Urology ESBL outbreak alert appears; open investigation view.
4. Replay into March 2026 → **novelty alert on 3 March** (first ICU MRSA in 323 days), then the MRSA cluster alert, flagged as hospital-acquired; show detection latency.
5. Dec 2025 → data-gap alert for PHC-S ("no data", not "no resistance").
6. A known ESBL carrier shows up on another ward → **carrier re-appearance alert**.
7. **Mock patient record** calls our API → cards for the patient and for the chosen antibiotic.
8. Switch to the Lab & stewardship role → TMP trend crossing ~20 % → guideline-review recommendation.
9. (If built) Ask the AI assistant a clinical question.
10. Close: plugs into a live lab feed (Mylab); same engine extends to other cases (§4.12).

---

## 7. Deliverables
- [ ] Working tool (local web app)
- [ ] Pitch deck mapped to the 4 judging criteria
- [ ] Demo script / replay presets
- [ ] README: how to run, methods used, limitations

---

## 8. Validation answer key (planted events): DO NOT HARDCODE

Found by exploratory analysis. Use these to **test** that the general detectors work and to
measure detection latency. The detectors must find them without knowing about them.

| # | Type | Event | Evidence |
|---|---|---|---|
| E1 | ANOM-01 / 02 | **ESBL E. coli outbreak, URO, ~2025-06-04 → 2025-07-05** (ESBL cases already elevated from late Mar 2025, a few more until Sep) | ~30 ESBL cases in 5 weeks vs 2–8 per quarter normally. Ceftriaxone R 21/42 in the 4-week block from 2025-06-09 vs 6 % baseline. Uniform profile (R: CIP 85 %, TMP 74 %; S: MEM, NIT). |
| E2 | ANOM-01 / 02 / 08 | **MRSA cluster, ICU, 2026-03-03 → 2026-03-27** | 13 cases vs 0–1 per quarter. 10 of 13 sampled ≥ 3 days after admission (hospital-acquired). First case came 323 days after the previous ICU MRSA → novelty alert on day 1. |
| E3 | ANOM-04 | **Data gap, PHC-S, 2025-12-08 → 2025-12-14** | Zero samples for 7 days; no other ward has more than 3 empty days in a row. |
| E4 | ANOM-03 | **Slow drift: E. coli trimethoprim resistance 14 % → 21 %**, Q4/2023 → Q3/2026, across all wards | Crosses the ~20 % empirical-use threshold around 2025. |
| E5 | NOTIF-01 / ANOM-08 | **Sentinel cases:** 12 CPE + 5 VRE scattered over 3 years. Most recent: VRE GER 2026-09-11 (first ever on GER), CPE MED-A 2026-09-21 (first on MED-A in 822 days), both inside the last 4 weeks as of 2026-09-27. | |
| E6 | PAT-02 | **Carrier re-appearances** (consequence of patient movement, not planted) | 352 of 491 ESBL carriers and 70 of 110 MRSA carriers later sampled on a different ward. |
| — | (built-in effect) | Urine E. coli CIP resistance: men 12.6 % vs women 6.0 % | Not an anomaly; supports STAT-07. |

Other minor statistical blips (single 4-week cells with z ≈ 3) are most likely noise. This is
exactly why STAT-08 matters.

**Detector results (slice 2, default config, full replay; checked by `backend/tests/test_slice2.py`)**

| # | First alert | Latency |
|---|---|---|
| E1 | Cluster URO ESBL 2025-06-07 (5 cases / 14 d vs 0.7 expected); rate shift URO urine E. coli (CRO, CIP, CXM) 2025-06-15 | ~3 days / ~11 days (weekly test) |
| E2 | Novelty ICU MRSA 2026-03-03 ("first in 323 days"); cluster 2026-03-07; S. aureus FOX/CLI rate shift 2026-03-29 | 0 / 4 days |
| E3 | Data gap PHC-S 2025-12-09 (2nd silent day) | 1 day |
| E5 | All 12 CPE + 5 VRE as sentinel alerts on the sample day, with "first on ward in N days" | 0 days |

Alerts not in the answer key over 3 years: cluster MED-B ESBL 2024-09-19 (3 cases, all hospital-acquired,
same weeks as a MED-B E. coli TZP rate shift) and cluster MED-A ESBL 2025-04-19 (5 vs 0.7); 11 other
novelty alerts (MRSA/ESBL first on a ward in ≥ 180 days). No false data-gap alerts.

**Slice 3 results** (checked by `backend/tests/test_slice3.py`)

| # | Result |
|---|---|
| E4 | Trend test (ANOM-03): the **only** significant trend among 527 location × specimen × organism × antibiotic series is all-locations urine E. coli TMP, +2.1 pp/year (q 0.003); the fitted line crosses 20 % in **2025 Q4**; calendar years 14 → 18 → 19 → 21 %. |
| Sex effect | Subgroup discovery (STAT-09) finds urine E. coli CIP men 14 % vs women 6 % (q 3e-10) by itself, at all locations, hospital, primary care, URO and PHC-N. |
| ANOM-07 | Detection latency from each alert's own onset (the earliest case it counted): E1 cluster 8 days after its first counted case (3 days after the answer key's 2025-06-04); E2 novelty 0 days, cluster 4 days; E3 1 day after the gap began; sentinels 0 days. Rate shifts read 20–27 days, because their onset is the first resistant case anywhere in the 4-week window. |

Other slice-3 findings (not in the answer key): subgroup differences at all locations for urine E. coli
TMP by onset (hospital-acquired 25 % vs 18 %) and in/outpatient (24 % vs 18 %), and for wound S. aureus
CLI by ward (ICU 16 % vs ED 0 %). 11 upward crossings of 20 % in the last 12 months; only URO
K. pneumoniae TMP (14 % → 32 %) has its whole interval above 20 %, the rest are within noise.

**Slice 4 results** (checked by `backend/tests/test_slice4.py`)

| # | Result |
|---|---|
| E1 | Profile similarity (ANOM-05): 26 of 29 E. coli cases share R: AMP CIP CRO CXM TMP, a profile 20 % of ESBL E. coli elsewhere had in the year before (p 2e-15) → "consistent with a single strain". 12 of the 30 case patients were sampled on other wards within 90 days (MED-A 4, ED 4, PHC-S 3, …). |
| E2 | 12 of 13 MRSA cases share R: CLI FOX vs 9 % of MRSA elsewhere (p 3e-12) → single strain. |
| E6 | Carrier registry (PAT-01): 491 ESBL, 110 MRSA, 12 CPE, 5 VRE carriers. Carrier re-appearance (PAT-02): 1,336 alerts over 3 years on hospital wards (~8.5 a week, ~1 per ward); routine, so kept out of the badge and replay pauses. |
| ANOM-09 | Multi-ward signal: 1 firing in 3 years on the organizers' data (ESBL K. pneumoniae R: CIP CRO CXM TZP on GER, MED-A, PHC-N in April 2025, 3 cases); the data has no planted spread. A planted two-ward spread (3 + 3 cases in 10 days, test only) is found. |

Other slice-4 findings: the MED-A ESBL cluster (Apr 2025, not in the answer key) has mixed profiles (2 of 3 match), so
it is probably not one strain. Therapy helper: on most wards no agent reaches 90 % coverage for UTIs, because
E. faecalis (~10 %) is never tested for most agents and counts as not covered.

---

## 9. Decisions log
| Date | Decision |
|---|---|
| 2026-10-16 | External EARS-Net/THL data is optional (reference only). |
| 2026-10-16 | Detection must use general methods; planted events serve only as a validation set. |
| 2026-10-16 | Slow-drift analysis is a separate, non-daily stewardship workflow (V6). |
| 2026-10-16 | Sentinel cases (CPE/VRE/etc.) are handled by the notification feature, rule-based. |
| 2026-10-17 | Three primary roles: Clinician, Infection control, Lab & stewardship. Health-centre GPs are part of Clinician; stewardship and annual reporting fold into Lab. |
| 2026-10-17 | Therapy helper (V2), ward alert strip and data-freshness badge live inside V1, not as separate pages. |
| 2026-10-17 | AI layer, if built, goes through OpenRouter. |
| 2026-10-17 | LIVE-03 and VIEW-10 are optional. NOTIF-05 (simulated external delivery) raised to S. |
| 2026-10-17 | **Frontend: React** (Vite + TypeScript) with **Motion** for animations. Chosen because the AI assistant is most reliable in React; Motion covers the replay animations. Backend: Python FastAPI (pandas/DuckDB, scipy/statsmodels), which doubles as the integration API. |
| 2026-10-17 | STAT-09 (automatic subgroup-difference discovery) raised to M. |
| 2026-10-17 | Integration API (§4.10) and the carrier registry (PAT-01) are requirements (M), both pull and push. |
| 2026-10-17 | Novelty alert: the mentor meant "not seen in years" (example: 20 years). |
| 2026-10-17 | We may plant our own scenarios in extension data (§4.11). |
| 2026-10-17 | "Beyond antibiotics" (§4.12) shelved. |
| 2026-10-17 | Varha angle is TBA / parked (§1). |
| 2026-10-17 | First-isolate rule is applied **within the analysed stratum and window** (e.g. per ward), the CLSI M39 convention for unit-specific antibiograms. A patient sampled on GER and URO counts once on each ward and once hospital-wide. |
| 2026-10-17 | Fallback hierarchy (STAT-04): ward → institution (all hospital wards / all health centres) → all locations. V1 cells show the ward's 4-week value (counts if n < 30) next to the 12-month value at the most specific level with n ≥ 30, marked H / P / A when it fell back. STAT-06 shrinkage not built (waiting on mentor). |
| 2026-10-17 | Traffic light: green < 10 %, amber 10–20 %, red ≥ 20 % (config). Intrinsic pairs show as hatched "Intrinsic R". |
| 2026-10-17 | Data freshness (VIEW-12) uses a per-ward Poisson silence test: with λ samples/day over the last 8 weeks, d silent days are flagged when exp(−λd) < 0.01 (delayed) or < 0.001 (stale). Busy wards flag after 1 day, ICU after ~3–4. Basis for ANOM-04. |
| 2026-10-17 | Build in slices (§12). Base features are built function-first with simple visuals; presentation and visual polish are deferred to the usability optimization phase (§4.13, slice 5). |
| 2026-10-17 | **Alert model:** each detector emits *firings* ("on day t, using only data ≤ t, this test was positive"). Firings of the same detector × ward × subject close together form one alert (episode); it stays active for a per-type hold period after its last firing, then is "resolved". Since no firing looks ahead, the whole timeline is computed once (~3 s, warmed at startup) and the alerts at any as-of are just the firings up to it, so replay shows alerts exactly when they would have fired. |
| 2026-10-17 | **ANOM-01 cluster:** daily Poisson test of new phenotype cases (repeat positives of a patient within 90 days removed) in the last 14 days vs the ward's own previous 12 months; runs on days with a new case, needs ≥ 3 cases. **ANOM-02 rate shift:** weekly (Sunday) one-sided Fisher exact test, last 4 weeks vs previous 12 months, first isolates per ward; gates n ≥ 10 recent, n ≥ 30 baseline, +10 pp; one alert per ward × specimen × organism listing every shifted antibiotic. **STAT-08:** Benjamini–Hochberg FDR (q = 0.05) across all hypotheses of the same evaluation day. |
| 2026-10-17 | **ANOM-04 data gap** uses the freshness silence test plus a 7-day low-volume test, but alerts only at p < 1e-6 (the badge keeps 0.001/0.01): ~10,000 ward-days are tested and daily volumes are over-dispersed, so badge-level α would raise ~30 alerts that are ordinary dips. |
| 2026-10-17 | **ANOM-08 novelty** covers MRSA and ESBL (gap ≥ 180 days, or never with ≥ 180 days of history) and organisms under 1 % of isolates (none currently). CPE/VRE are sentinels; their alert carries the same "first on this ward in N days" note instead of a second alert. Sentinel meropenem-R is limited to Enterobacterales (Pseudomonas has a 6 % background). |
| 2026-10-17 | **Severity (NOTIF-04):** sentinel = critical, cluster = high, rate shift / novelty / data gap = medium. **Triage (NOTIF-06)** is stored in `backend/.state/triage.json` with the as-of date it was taken at and applies from that date on, so replaying earlier dates shows alerts as they were. Dismissing suppresses repeats of the same detector × ward × subject for 90 days. |

| 2026-10-17 | **Replay (LIVE-02/04):** the cursor steps forward (1 day or 1 week) only once every open view has loaded the previous step, so the backend sets the pace. Alerts first raised during a step are listed under the replay bar, and replay can pause on them. "Jump to" lists every alert raised up to today (built from the alert history, not the answer key) and starts 7 days before its onset. |
| 2026-10-17 | **ANOM-07 onset:** an alert's onset is the earliest case its first firing counted (cluster: first case in the 14-day window; rate shift: first resistant first isolate in the 4-week window; data gap: the day after the last sample; sentinel / novelty: the case itself). Detection latency = first alert − onset, shown on every alert. |
| 2026-10-17 | **ANOM-03 trends:** Cochran–Armitage test over calendar quarters (first isolates per quarter; the current quarter runs to as-of) for every location (all, institutions, wards) × specimen × organism × antibiotic. Gates: ≥ 6 quarters, ≥ 100 isolates, ≥ 5 pp fitted change; BH FDR across all eligible series. The fitted line is the matching weighted least squares. Threshold crossings: last 12 months vs the 12 before against 20 %, n ≥ 30 in both, shown as within noise unless the 95 % CI is past the line. Trends live in V6, not the alert inbox. |
| 2026-10-17 | **STAT-09 subgroups:** first isolates are taken once per scope and window, then compared across sex, age band, hospital-acquired, in/outpatient, home area and ward (when the scope has several). Levels need n ≥ 30; Fisher exact (2 levels) or chi-square, tested only when the spread is ≥ 5 pp; BH over every comparison with enough data. Shown under My Ward (12 months, the selected ward) and in V6. |
| 2026-10-17 | **STAT-07 defaults:** only urine E. coli by sex is split by default (config `DEFAULT_SPLITS`). Any organism can be split by sex, age band, onset, in/outpatient or home area from a subgroup finding. Onset and in/outpatient are not split by default: STAT-09 surfaces them where they matter (e.g. TMP by onset, hospital-wide) instead of doubling every table. |
| 2026-10-17 | **DATA-05 ingestion:** batches in the CSV schema (`POST /api/ingest`), validated as a whole (keys, references, S/R only); only new rows are joined; the alert engine keeps firings before the batch's earliest sample date and re-runs the detectors from there (tested equal to a full rebuild). "Today" is now the last sample received (`AEI_AS_OF` can pin it); clients poll `/api/status` and follow. `AEI_HOLD_BACK_FROM` holds data back at startup so the feed status page can receive it day by day (demo). |
| 2026-10-17 | **V5 overview:** wards × weeks of new ESBL / MRSA / VRE / CPE cases, or a key resistance rate (EARS-Net-style indicators in config) per 4-week block or quarter, with % only at n ≥ 30. Cells are ringed where an alert was raised. |

| 2026-10-17 | **VIEW-08 roles** moved into slice 4 (user request). A role picker on first visit (no login; in production the role comes from SSO). Clinician → My Ward with their own ward, nav limited to My Ward and Alerts, aggregates only; Infection control → Alerts; Lab & stewardship → Feed status. Patient-level views (line lists, carriers, spread, patient pages) are hidden in the clinician role (NF-03, UI-level only: the API itself is not access-controlled yet). |
| 2026-10-17 | **PAT-01/02 carriers:** a patient is a carrier from their first MRSA/ESBL/VRE/CPE positive; flags don't expire (config `CARRIER_FLAG_DAYS`; clearing needs screening data we don't have). A known carrier's new sample on a **hospital** ward raises a "known carrier sampled" alert on the sample day, unless the ward sampled them in the last 30 days. Severity medium and **routine**: ~1 per ward per week, so these are shown to the ward and in their own inbox section, but don't count in the infection-control badge, the replay jump list or pause-on-alert. Health-centre visits don't alert (standard precautions). |
| 2026-10-17 | **ANOM-05 profiles:** profile = agents resistant among those tested, intrinsic resistance left out; two isolates match when they agree on every agent both were tested for (≥ 3). A cluster is "consistent with a single strain" when ≥ 70 % of its cases match the dominant profile and a binomial test against the same phenotype × organism in the previous year gives p < 0.01. Shown in V4, not used to raise or suppress alerts. |
| 2026-10-17 | **ANOM-09 multi-ward:** per phenotype × organism × core profile (urine-only agents left out so specimens compare), 28-day window vs the hospital-wide baseline (Poisson, BH FDR across active profiles), and the cases outside the busiest ward must also exceed their own expected count (p < 0.05, ≥ 2 cases). Without that second test every single-ward cluster of a common profile would also read as "multi-ward". Alert ward = several (listed); severity high; no direction claimed. |
| 2026-10-17 | **V2 therapy helper (WISCA):** coverage = Σ organism share × susceptibility over first isolates of the infection's specimen in the last 12 months, for the ward's population matching the patient filters, falling back ward → institution → all below 30 isolates. 95 % interval by Monte Carlo (Dirichlet shares × Beta susceptibilities, Jeffreys priors). Intrinsic resistance and never-tested pairs count as not covered (agents untested on > 50 % of the population are listed apart). The FOX screen is not offered; S. aureus β-lactams are inferred from it (EUCAST expert rule). Reserve agents (meropenem) are tagged. Shown inside My Ward using its ward, specimen and patient filters. |
| 2026-10-17 | **API-02/03 CDS Hooks:** discovery at `GET /api/cds-services`; `aei-antibiotic-choice` (order-select) and `aei-patient-context` (patient-view) return standard cards (summary, indicator, detail, source, links). The context takes plain fields (ward, infection, sex, age, antibiotic) next to `patientId` and a FHIR `draftOrders` bundle; `as_of` as a query parameter keeps replay consistent. |
| 2026-10-17 | **NOTIF-03/05, API-04 delivery:** subscriptions (role, wards, minimum severity, types, routine on/off, events alert / carrier_flag / digest, channel webhook / email / Teams) in `backend/.state/subscriptions.json`, seeded with five demo recipients. Messages derive from the alert timeline, so the notifications view shows what was sent up to the time cursor (replay-consistent). Live delivery happens on ingest: webhooks are real HTTP POSTs (the mock patient record's inbox receives them); email and Teams are simulated (logged). Weekly digest on Mondays. |
| 2026-10-17 | **Alert chart window:** an alert's chart now ends 4 weeks after its last signal (or at as-of), so an old alert shows its own period instead of the weeks before today. |
| 2026-10-17 | **UX-01 Varha hierarchy:** one main hierarchy by where the sample was taken: Varha → institution → ward → (existing) cell / alert / cases / patient. Lab & stewardship land on Varha, infection control on Tyks, clinicians stay on their ward. In the demo Varha = Tyks + PHC-N + PHC-S; PHC-N and PHC-S are separate institutions here (the STAT-04 fallback still groups them). Other Varha hospitals (Loimaa, Vakka-Suomi, Salo) are greyed placeholders labelled "not in demo data": shows the scale without inventing results; levels are data-driven so real hospitals would fill in. No extension data needed. Schematic layout, no real map. Home area is a community lens on the Varha page, not a level. Three roles stay (no separate Varha-management role). |
| 2026-10-17 | **UX-02/03 anomalies only:** overview pages show anomalies, not everything. Anomaly = active alert (new or ongoing, any type) or feed problem (delayed / stale / data gap). Chronic red cells are *not* anomalies (they would keep every count non-zero). Higher levels show anomaly counts per child, never an overall resistance % (averages hide a 30 % ward inside a 9 % hospital). Children without anomalies collapse into one line naming them, so "calm" is never confused with "no data". Colour means action: only anomalies get colour, normal is quiet grey. |
| 2026-10-17 | **UX-05 clinician view = what not to use:** prescribers already know what they want; they need to know when *not* to use it. The "avoid" list comes from per-organism resistance (cells above the threshold for the infection's main organisms), not WISCA coverage, because untested E. faecalis caps UTI coverage near 90 % for nearly every agent. Each line carries since when, direction and n. In the moment of prescribing, the CDS order-select hook (API-02) does the same in the patient record. |
| 2026-10-17 | **UX-06 notifications demoted:** alerts are first-party (inbox, overview, detail); notifications are delivery (email / Teams / webhook) and live under settings. Clinicians lose the badge and the alert strip; their ward's alerts appear inside the exceptions list. Infection-control nav becomes Overview (home) · Alerts · Spread · Carriers · ⚙. |

## 10. To-do & open questions

### 10.1 To-do list
**Ask the mentor (Tyks / Mylab):**
- [ ] Hospital-acquired convention: is "day ≥ 3 after admission" the rule they use (DATA-03)?
- [ ] Shrinkage / smoothed estimates: acceptable and understandable for clinicians, or prefer plain fallbacks (STAT-06)? (Or just show info for the "non-normal" cases?)
- [ ] Notifications: should a ward doctor also see other wards' alerts, e.g. neighbouring or feeder wards (NOTIF-03)?
- [ ] Roles: are our 3 roles the right ones? Is there a stewardship team at Tyks that would use trends (VIEW-08, R3)?
- [ ] Local empirical-therapy threshold: is ~20 % the convention in Finland / at Tyks?
- [x] ~~"Bacteria not seen for 20 minutes": what time scale?~~ Resolved: years (see ANOM-08).
- [ ] How is carrier status (MRSA/ESBL risk information) handled in patient records today? Would they prefer we push carrier flags to their system, or that their system queries ours (API-03/04)? (Both are built.) When is a flag cleared, and do health centres need carrier alerts too?
- [ ] Therapy helper: which agents are reserve agents locally, and should untested organisms (E. faecalis) count as not covered?
- [ ] Varha scope: should the pitch position the tool as Varha-wide (all hospitals, health centres, elderly care), or Tyks-only? (Our default, §9 UX-01: Varha-ready, demo shows Tyks + 2 health centres with other hospitals as placeholders.)

**Team:**
- [x] Choose the tech stack: React + FastAPI (§9).
- [ ] Decide which remaining *(proposed)* requirements (EXT) to commit to, and set their priorities.
- [x] Figure out how the Varha angle should work in the tool before building anything for it (UX-01, decided in §9).

### 10.2 Open questions
- Hackathon timeline and submission format?

---

## 11. Explainers for ❓ items

**First isolate (DATA-02).** When an infection doesn't respond to treatment, doctors sample
the patient again, often several times. Resistant infections fail treatment more often, so
they get sampled more. If every sample counted, one stubborn ESBL patient sampled five times
would count as five resistant cases, and the ward's resistance would look worse than it is.
Counting only each patient's first isolate (per organism, specimen type and period) means
one patient = one vote. In this data: 24,571 isolates but only 17,517 unique patient ×
organism × specimen combinations; 3,752 combinations repeat, one up to 14 times, and 802
isolates repeat the same combination within 30 days.

**Why the small-number techniques matter at all.** The doctor wants the *last 4 weeks* on *their ward*. But a ward
only produces a handful of isolates per organism per month (typically 10–60, often < 30;
ICU S. aureus ~11 per 4 weeks). Small numbers bounce around randomly: 3 resistant out of
10 reads as "30 %", but it could easily have been 1/10 or 5/10 by pure chance. The view
the doctor wants most is the one with the least reliable numbers. These techniques make
that visible and safe.

- **Confidence interval (STAT-02):** the range the true value very likely lies in. For
  3/10 resistant, the 95 % interval is roughly **11 %–60 %**, so the "30 %" means very
  little. For 30/100 it's ~22 %–40 %, which is much tighter. Show it as a bar or as a tooltip.
- **Show counts (STAT-03):** "3 / 10" tells a clinician immediately that the sample is
  small; "30 %" hides it.
- **Fallback to a broader group (STAT-04):** if the ward has too few isolates, show the
  number for the whole hospital (or all health centres) instead, with a label like
  "Showing hospital-wide data: too few isolates on ICU".
- **Fallback to the annual figure (STAT-05):** same idea along time instead of place.
  12 months has ~13× the data of 4 weeks, so use it as the main number and show the
  4-week value as "recent signal".
- **Shrinkage (STAT-06):** a middle ground between the two fallbacks. Instead of choosing
  ward *or* hospital, blend them: with few ward isolates the estimate leans on the hospital
  value, and with many it trusts the ward. One stable best-guess number. (Statistically this
  is "empirical Bayes" / beta-binomial smoothing.)
- **Weighted syndromic antibiogram (VIEW-04, a.k.a. WISCA):** a doctor treating a UTI doesn't yet
  know *which* organism it is. This answers "what fraction of this ward's UTIs would
  antibiotic X cover?" by weighting each organism's susceptibility by how often that organism
  causes UTIs there. That is exactly the question asked at the bedside.

---

## 12. Implementation slices
Work is split into vertical slices, one commit series each. Update the status here.

| # | Slice | Main requirements | Status |
|---|---|---|---|
| 1 | Data layer + statistics engine + V1 My Ward | DATA-01–04, 06, 07 · STAT-01–05 · LIVE-01 · VIEW-01/02/12 (core) · API `/meta`, `/antibiogram`, `/freshness` | done |
| 2 | Detectors + alerts | NOTIF-01/02/04/06 · ANOM-01, 02, 04, 06, 08 · STAT-08 · V3 inbox, V4 detail, V1 alert strip, V7 feed status | done |
| 3 | Replay, trends, discovery | LIVE-02/04 · ANOM-03, 07 · V6 trends, V5 heatmap · STAT-07 defaults, STAT-09 · DATA-05 incremental | done |
| 4 | Patients + integration | PAT-01–03 · API-02–05 · NOTIF-03/05 · V2 therapy helper · V10 spread · V11 mock EHR · ANOM-05/09 · VIEW-08 roles (moved up from slice 5) | done |
| 5 | Usability optimization | UX-02–06 (exceptions-first overview, Varha drill-down, clinician "avoid" view, notifications to settings, visual polish; UX-01 design decided) · role landing pages polish · VIEW-09 | next |
| 6 | AI, extension data, delivery | AI-01–04 · EXT-* · README, demo presets | |
