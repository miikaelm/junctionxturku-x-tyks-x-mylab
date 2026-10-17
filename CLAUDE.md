# CLAUDE.md

Hackathon project (JunctionX Turku, Tyks Laboratories × Mylab): a continuously updated
antimicrobial-resistance surveillance tool ("AEI – Antibiotic Efficacy Indicator").

**Read [PROJECT.md](PROJECT.md) first.** It is the single source of truth: the challenge,
judging criteria, users and views, requirements with IDs and status checkboxes, domain rules,
the validation answer key, the decisions log and open questions.

## Working rules
- When you finish or start a requirement, update its checkbox in PROJECT.md (`[ ]` → `[~]` → `[x]`).
- Record new decisions in PROJECT.md §9 (with date) and resolve open questions in §10.
- Anomaly detection must use **general methods**. Never hardcode the planted events in
  PROJECT.md §8; they are for validation only.
- Resistance percentages must follow the domain rules in PROJECT.md §5 (first isolate per
  patient × species × specimen per period, n ≥ 30, intrinsic resistances excluded from alerts).
- Every computation must respect the global as-of date (time cursor): use no data after it.

## Layout
- `backend/`: Python 3.11, FastAPI, managed with `uv`. Package `app/`:
  - `config.py`: paths and thresholds (all tunables live here, NF-04)
  - `data/`: loading, joins, first-isolate, hospital-acquired flag (DATA-*)
  - `stats/`: resistance rates, CIs, fallbacks, subgroup discovery (STAT-*)
  - `detectors/`: anomaly detectors (ANOM-*)
  - `alerts/`: alert model, sentinel rules, notifications (NOTIF-*)
  - `patients/`: carrier registry (PAT-*)
  - `api/`: HTTP routes under `/api` (API-*)
  - Tests in `backend/tests/`.
- `frontend/`: React 19 + TypeScript + Vite + Motion. `src/api/` (backend client),
  `src/views/` (V1–V11), `src/components/`. Vite proxies `/api` to `localhost:8000`.

## Commands
- Backend: `cd backend && uv sync`, `uv run uvicorn app.main:app --reload` (port 8000), `uv run pytest`
- Frontend (needs Node.js): `cd frontend && npm install && npm run dev` (port 5173)

## Data
- `synthetic_microbiology_dataset/`: CSVs (UTF-8, comma, ISO dates) plus a README with the column docs.
- Join chain: `patients` → `cultures` (patient_id) → `isolates` (culture_id) → `susceptibility` (isolate_id).
- Period 2023-10-02 → 2026-09-27; the scenario's "today" is 2026-09-27.
- Source briefs: `Tyks x Mylab case informations.pdf`, `Website Text.txt`, `Participant_guide.pdf`.
