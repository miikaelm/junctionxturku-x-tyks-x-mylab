# Demo notes

Dates, patients and what each step should show. The demo tools (date, replay, jump to an alert,
the mock patient record) are in the bottom bar marked "Demo only".

## Before the demo

1. Start the backend and wait for the warm-up lines in its console (about 2–3 minutes):
   `AEI warm-up: 2026-09-27 ready in …` … `AEI warm-up done: N dates in … s`. The pages for the
   dates below are then fast (the stewardship page is ~10 s per date cold, under 1 s warmed).
2. Clear earlier triage and stewardship reviews if you want a clean run:
   `curl -X DELETE localhost:8000/api/triage`, and delete `backend/.state/stewardship.json`.
3. Close the mock record's webhook inbox if it has old messages: `curl -X DELETE localhost:8000/api/mock-ehr/inbox`.

## Warmed dates

Computed at startup (`app/demo.py`): today, the mock record's date, and the day every cluster,
multi-ward and data-gap alert was raised (from the alert history, not the answer key).

| Date | What is there |
|---|---|
| 2026-09-27 (today) | Stewardship findings (trimethoprim crossed the limit), VRE on GER and CPE on MED-A in the last 4 weeks |
| 2025-06-07 | URO ESBL cluster raised (5 cases in 14 days, expected 0.7) |
| 2025-06-27 | URO outbreak in full: ceftriaxone, ciprofloxacin, cefuroxime risen; **mock record date** |
| 2025-12-09 | PHC-S data gap (no samples for 2 days, usually ~7 a day) |
| 2026-03-07 | ICU MRSA cluster (novelty alert came on 2026-03-03, the day of the first case) |
| 2025-04-10, 2025-04-19, 2024-09-19 | Multi-ward ESBL K. pneumoniae, MED-A and MED-B ESBL clusters (not in the answer key, see PROJECT.md §10) |

"Jump to a past alert…" in the demo bar sets the date to the day the alert was raised and stays
there; ▶ Replay plays forward from it.

## Mock patient record (EHR): 27 Jun 2025, Urology

Open it from the demo bar ("Open EHR demo →"). If the date differs, a yellow bar offers to go to
27 Jun 2025. The ward list on the left holds the two patients.

### Patient A: P006127 (man, 89, on URO since 19 Jun, day 9)

The ESBL outbreak patient who was an MRSA carrier before ("grandma" story: GER in 2024, URO now).

| Step | AEI should show |
|---|---|
| Open the record (patient-view) | Banner badges ESBL, MRSA. Risk information: known ESBL carrier (positive Jun 2025, URO); known MRSA carrier (positive Jan 2024, GER); part of the active ESBL cluster on URO; part of the resistance shift on URO. |
| Lab results tab | 20 Jun 2025 urine E. coli ESBL, R: AMP, CXM, CRO, CIP, TMP; S: the rest. |
| Order: urinary tract infection + **ceftriaxone** (order-select) | Critical: "This patient's own E. coli was resistant to ceftriaxone (urine, 2025-06-20, URO)". Warning: ceftriaxone has risen on URO in the last 4 weeks, likely cause the ESBL cluster (17 of 17 resistant isolates are its cases). Alternatives: mecillinam (Access), piperacillin-tazobactam (Watch), with "Change to" buttons. Active ESBL cluster on URO. |
| Sign order (order-sign) | "Before you sign" box with the two warnings, "Change to mecillinam", or "Sign anyway" with a reason. |
| Change to mecillinam, sign | No local warning; the patient's own E. coli was susceptible. Signing goes straight through: "Signed. AEI had nothing to add." |

### Patient B: P006301 (woman, 73, on URO since 12 Jun, day 16)

No carriage, no positive culture in the last year (urine on 24 Jun: no growth): an empirical
choice, where the ward's figures are what matters.

| Step | AEI should show |
|---|---|
| Open the record | Risk information: "No notices". |
| Order: urinary tract infection + **trimethoprim** | Critical: avoid trimethoprim for a UTI on URO, E. coli 25 % resistant (AEI uses her group, women 65–79, where E. coli is the only main organism). Alternatives: nitrofurantoin, mecillinam (Access), piperacillin-tazobactam (Watch). Active ESBL cluster on URO. |
| Sign order | "Before you sign" box; "Change to nitrofurantoin" (or sign anyway with a reason: the order list then says the warning was overridden and why). |
| Nitrofurantoin, sign | No local warning for her group (women 65–79). Goes straight through. |
| Try ciprofloxacin | Warning: resistance has risen on URO in the last 4 weeks. |

Overrides and accepted suggestions are sent back as CDS Hooks feedback:
`GET localhost:8000/api/cds-services/aei-antibiotic-sign/feedback`.

## National reference

Every antibiogram cell's details, trend chart and stewardship finding compare with Finland
(THL Finres 2023). Example at today: urine E. coli trimethoprim is 20 % in our data against 16 %
nationally; most other pairs sit close to the national figures.
