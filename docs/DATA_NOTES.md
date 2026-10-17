# Data notes (quick reference, so the dataset doesn't need re-profiling)

Profiled 2026-10-17 on `synthetic_microbiology_dataset/`. Column docs: that folder's README.
Planted events / answer key: PROJECT.md §8 (validation only, never hardcode).

## Shape
| Table | Rows | Key | Notes |
|---|---|---|---|
| patients | 10,000 | patient_id | sex F 4,989 / M 5,011; home_area North/South/East/West/Centre (~2k each); birth_year |
| cultures | 46,792 | culture_id | one sample; has ward, specimen, result, age_years, admission_date (inpatients only) |
| isolates | 24,571 | isolate_id (`<culture_id>-<n>`) | 0–2 per culture; organism, quantity, esbl/mrsa/vre/cpe 0/1 |
| susceptibility | 172,381 | isolate_id × antibiotic_code | S/R only; also repeats culture_id + organism; guideline "EUCAST 2023…2026" |
| antibiotics, wards | 13, 9 | code tables | `reported_for` = all / urine |

- Dates only (no times). Range 2023-10-02 (Mon) → 2026-09-27 (Sun) = 1,092 days, 156 ISO weeks.
- Data is clean: no orphans, no missing values except `admission_date` for outpatients.
- `ward_type == "in"` ⇔ `admission_date` present (19,674 cultures). Out = 27,118.
- Read CSVs with `parse_dates=["sample_date", "admission_date"]`.

## Cultures
- Specimen: urine 32,748 · wound 7,070 · blood 6,974.
- Result: positive 22,192 · negative 20,946 · mixed_growth 3,654 (urine 3,282, wound 372, blood 0).
- n_isolates: 0 → 24,600 · 1 → 19,813 · 2 → 2,379.
- Age (from `age_years`, per culture): median 66, IQR 40–77. Bands: 0–17: 2,525 · 18–64: 19,407 ·
  65–79: 14,722 · 80+: 10,138. No pediatric ward; children spread across wards.
- Days from admission to sample (inpatients): 0–21, median 3. `sample − admission ≥ 2`
  (hospital-acquired by our rule) = 13,960 of 19,674 inpatient cultures (71 %).
- Volume: ~300 cultures/week total (sd 26, range 224–362). **No weekday/weekend effect** (≈6.6–6.8k per weekday).
- Cultures/day by ward: ED 9.0 · PHC-N 7.9 · PHC-S 7.9 · MED-A 3.9 · URO 3.4 · SURG 3.3 · GER 3.0 · MED-B 2.7 · ICU 1.8.
- Longest run of days with zero samples: PHC-S 7 (the planted gap, E3) · ICU 3 · GER/MED-A/MED-B/SURG 2 · URO 1 · ED/PHC-N 0.

## Wards
ED (out, hospital) · MED-A, MED-B, SURG, URO, ICU, GER (in, hospital) · PHC-N, PHC-S (out, primary_care).
URO has no wound samples; PHC wards have no blood samples; MED-B has no wound samples.

## Isolates
| Organism | Isolates | urine / wound / blood | Phenotypes |
|---|---|---|---|
| Escherichia coli | 11,534 | 10,619 / 613 / 302 | ESBL 396, CPE 2 |
| Staphylococcus aureus | 3,017 | 629 / 2,127 / 261 | MRSA 111 |
| Enterococcus faecalis | 2,385 | 1,794 / 503 / 88 | VRE 5 |
| Klebsiella pneumoniae | 2,384 | 2,035 / 256 / 93 | ESBL 121, CPE 4 |
| Proteus mirabilis | 1,725 | 1,258 / 427 / 40 | CPE 2 |
| Pseudomonas aeruginosa | 1,653 | 845 / 751 / 57 | – |
| Citrobacter freundii | 874 | 605 / 242 / 27 | CPE 3 |
| Klebsiella oxytoca | 621 | 587 / 0 / 34 | CPE 1 |
| Staphylococcus saprophyticus | 378 | 378 / 0 / 0 | – |

Totals: ESBL 517, MRSA 111, VRE 5, CPE 12. Quantity: urine `>=10^5`/`10^4`/`10^3`, wound `+`/`++`/`+++`.

## Which antibiotics are tested on which organism (overall % R, all isolates)
| | AMP | MEC | TZP | FOX | CXM | CRO | CAZ | MEM | CIP | TMP | NIT | VAN | CLI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E. coli | 36 | 3 | 4 | | 8 | 4 | | 0 | 8 | 18 | 0 | | |
| K. pneumoniae | **100 IR** | 5 | 7 | | 13 | 7 | | 0 | 10 | 15 | 34 | | |
| K. oxytoca | **100 IR** | 5 | 5 | | 9 | 2 | | 0 | 6 | 8 | 8 | | |
| P. mirabilis | 16 | 2 | 1 | | 4 | 1 | | 0 | 6 | 19 | **100 IR** | | |
| C. freundii | **100 IR** | 11 | 17 | | 41 | 14 | | 0 | 6 | 13 | 4 | | |
| P. aeruginosa | | | 9 | | | | 8 | 6 | 12 | | | | |
| S. aureus | | | | 4 | | | | | | 5 | 1 | 0 | 5 |
| S. saprophyticus | | | | | | | | | | 4 | 2 | | |
| E. faecalis | 0 | | | | | | | | | | 1 | 0 | |

- Empty = never tested (pair absent from the data). MEC/TMP/NIT appear only on urine isolates.
- IR = intrinsic resistance (EUCAST ERP v1.2); these are the only 100 % pairs. FOX = MRSA screen (FOX R ⇔ mrsa=1).
- MEM R in Enterobacterales ⇔ cpe=1 (12 isolates, all CPE). Pseudomonas has 92 MEM R with cpe=0
  (6 % background), so a "any meropenem R" sentinel rule must be limited to Enterobacterales.

## Small-number reality (first isolates per ward, as of 2026-09-27)
- **4 weeks:** almost every ward × organism cell is < 30. Only urine E. coli on ED (42), URO (32),
  PHC-N (66), PHC-S (73) reaches 30. Blood: 0–3 per ward. ICU urine: ~0.
- **12 months:** urine E. coli ≥ 30 everywhere except ICU (28); urine K. pneumoniae / E. faecalis /
  Proteus ≥ 30 on most big wards; wound S. aureus ≥ 30 on ED/GER/ICU/MED-A/SURG/PHCs; blood mostly < 30.
- ⇒ Fallbacks (place: ward → institution → all; time: 4 wk → 12 mo) are the normal case, not the exception.

## Repeats / first-isolate rule
24,571 isolates → 17,517 unique patient × organism × specimen; 3,752 combos repeat (max 14);
802 isolates repeat the same combo within 30 days. 73 % of patients appear on ≥ 2 wards.
Our convention: first isolate is taken *within the analysed stratum and window* (see PROJECT.md §9).

## Known effects (built into the generator, not anomalies)
- Urine E. coli CIP: men 12.6 % vs women 6.0 %.
- Mixed growth rate differs by ward (ICU ~2 %, GER up to 11 %).
