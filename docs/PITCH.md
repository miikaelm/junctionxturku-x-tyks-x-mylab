# Pitch outline

Working outline for the 2-minute video and the 10-minute final presentation. Key points and
timings only; the wording comes later. (docs/DEMO.md stays as the technical demo checklist.)

## What the judges are really looking for

- **Not another dashboard.** Many teams will show the same thing: an antibiogram, some charts, a
  list of anomalies. The brief says this outright ("too easy, won't create real value"). The
  judges want to see a tool that someone would actually open on a busy day.
- **Usefulness over analysis.** Finding the outbreaks is the easy part. Any team, or any AI model,
  can do it. What wins is the right answer reaching the right person at the moment they decide.
- **Continuous, not annual.** The whole point is replacing a once-a-year hospital report with
  something that updates as results come in.
- **Real workflow.** The judges are from a lab (Tyks Laboratories) and a lab-system vendor (Mylab).
  Doctors live in the patient record, not in a separate surveillance tool. Fitting into that
  workflow is the credible story.
- **Honest numbers.** Their hints (first isolate, n ≥ 30) test whether we understand that small
  numbers lie. Show that we handle it, but in one sentence, not a slide.
- **Versatile.** Different people need different things from the same data.

## What we pitch

**One thesis:** the analysis is the easy part; the hard part is making it useful to busy people.

**The foundation** (said quickly, as a list; everyone has some version of this):
- **Live Replay** (working name): the tool runs as if any day were today and plays results in
  day by day. This shows it updating continuously, the way a live lab feed would.
- Explore tables: every infection × antibiotic combination, filterable by ward, patient group
  and period, with 4-week and 12-month figures side by side.
- Honest statistics: first isolates, at least 30 isolates per figure, uncertainty shown, and a
  wider level when a ward has too few.
- What it found, among others: the URO ESBL outbreak (3 days after it began), the ICU MRSA
  cluster (day 1), the slow trimethoprim drift past 20 %, the health-centre data gap, every
  CPE/VRE case on its day. All with general methods; nothing hardcoded.

**The main part: three users, three designs.** All three are busy, so each gets a decision, not a
dashboard.

1. **Clinician: "what should I not use, and what instead?"**
   - My Ward opens on what to avoid on this ward right now, new rises first, with the reason in
     words. Everything else is one click away.
   - **The key point: it is built to work inside the patient record.** When a doctor orders an
     antibiotic, the tool checks it against this patient's own results and this ward's recent
     resistance, suggests alternatives (preferring narrow-spectrum drugs) and lets the doctor
     switch with one click or sign anyway with a reason. It uses CDS Hooks, a standard that
     patient-record systems already support.
2. **Infection control: "is something spreading?"**
   - Opens on what is abnormal now, from the whole county down to the ward.
   - They triage possible outbreaks (investigating, confirmed, dismissed). Evidence includes
     whether cases share the same resistance profile, i.e. probably the same strain.
   - Their decision flows to clinicians: an outbreak shows on that ward's view and in the patient
     record until infection control dismisses it as a false alarm.
3. **Stewardship: "what is slowly getting worse?"**
   - Long-standing problems and slow drifts, not daily alarms: e.g. trimethoprim resistance
     crossing the 20 % limit for empirical use, compared with the Finnish national figure.
   - Each finding has an owner and a status, so it becomes a guideline change instead of a chart
     nobody acts on.

## 2-minute video (absolute max 2:00, aim for 1:50)

| Time | Length | Content | On screen |
|---|---|---|---|
| 0:00 | 15 s | **Problem.** Tyks reports resistance once a year, for the whole hospital. A doctor choosing an antibiotic tonight needs their own ward, now. | Annual report vs a ward view |
| 0:15 | 10 s | **Thesis.** Finding anomalies is easy, AI can do it. Our focus: getting the answer to busy people at the moment they decide. Three users. | Title card with the three roles |
| 0:25 | 35 s | **Clinician in the patient record.** Patient on Urology, doctor orders ceftriaxone. The tool flags: this patient's own E. coli is resistant, and ceftriaxone resistance on this ward has risen in the last month. Suggests mecillinam; one click to switch, then sign. Brief glimpse of My Ward's avoid list. | Mock patient record, 27 Jun 2025, patient P006127 |
| 1:00 | 25 s | **Infection control.** Opens on what's abnormal: the Urology ESBL outbreak, same strain profile, so it's real. Mark it as investigating; the Urology clinicians already see it in their view and in the record (a false alarm, once dismissed, disappears for them). | County → Tyks → Urology, alert detail, triage |
| 1:25 | 15 s | **Stewardship.** Trimethoprim crossed 20 % resistance; Finland is at 16 %. An owned finding, not just a chart. | Stewardship finding with the trend chart |
| 1:40 | 15 s | **Foundation and close.** Live Replay through three years of data, every combination explorable, honest numbers. Close with the tagline. | Quick montage: replay playing, Explore table |

## 10-minute final presentation

| Time | Length | Part | Key points |
|---|---|---|---|
| 0:00 | 1 min | **Live opening** | The problem in one human example (doctor at night, annual report). The thesis: analysis is easy, usefulness is hard. Who we are. "Here's two minutes of it." |
| 1:00 | 2 min | **Video** | As above. |
| 3:00 | 1 min | **Slide: three users, three designs** | Busy people, so a decision first and detail on demand. What each one opens on. How they connect: infection control's triage feeds the clinicians. |
| 4:00 | 1.5 min | **Slide: it lives in the patient record** | Why: doctors won't open another tool. The order is checked against the patient's own results and the ward's recent resistance. Alternatives ordered narrow-spectrum first. Overrides with reasons are fed back, so stewardship learns why guidance is ignored. Uses a standard (CDS Hooks) plus push notifications, so it can plug into existing systems. |
| 5:30 | 1 min | **Slide: alerts people can trust** | Few alerts, each with a reason in words. Own baselines per ward, correction for testing many combinations. Example: two real excesses outside the planted events, which the tool's own evidence (mixed strains) lets infection control dismiss quickly. |
| 6:30 | 1 min | **Slide: the foundation** | Short list: Live Replay (continuous updating), Explore tables, honest statistics, what it detected and how fast. "Necessary, but not where the value is." |
| 7:30 | 0.5 min | **Slide: scale** | Built for the whole county (Varha → Tyks/health centres → ward); compares with the Finnish national figures. |
| 8:00 | 1 min | **Slide: next steps** | Connect to the real lab feed (Mylab). Pilot on one ward. AI explanations written only from the computed numbers. The same pattern works for other lab signals. |
| 9:00 | 1 min | **Close and buffer** | Repeat the thesis in one line. Leave time for questions or overrun. |

## Open decisions

- Final name for Live Replay.
- Tagline.
- Whether the video shows the date jumping between demo dates (Jun 2025 for the outbreak and the
  patient record, Sep 2026 for stewardship), or we explain it in one line.
- Whether an AI feature is built before the deadline, or only mentioned as a next step.
