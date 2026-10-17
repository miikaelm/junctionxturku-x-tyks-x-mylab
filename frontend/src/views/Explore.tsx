import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { api, type Antibiogram as AntibiogramData, type Specimen } from "../api/client";
import { Antibiogram } from "../components/Antibiogram";
import { CellDetail } from "../components/CellDetail";
import { Segmented } from "../components/FilterBar";
import { Legend } from "../components/Legend";
import { fmtDate } from "../lib/format";
import { useFetch, useLocalStorage } from "../lib/hooks";
import { ROLES } from "../lib/roles";
import { useApp } from "../state/AppContext";

type PeriodMode = "rolling" | "year" | "custom";

interface ExploreState {
  location: string;
  specimen: Specimen;
  ward_type?: "in" | "out";
  home_area?: string;
  organism?: string;
  antibiotic?: string;
  sex?: "F" | "M";
  age_band?: string;
  hospital_acquired?: boolean;
  period: PeriodMode;
  year?: number;
  start?: string;
  end?: string;
}

const INITIAL: ExploreState = { location: "hospital", specimen: "urine", period: "rolling" };

function daysBefore(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

/**
 * Explore (VIEW-02): the whole antibiogram behind every filter the data has — place (ward,
 * institution, in/outpatient, home area), what (specimen, organism, antibiotic), who (sex, age,
 * onset) and when (4 weeks + 12 months, a calendar year or any period). For lab and infection
 * control; clinicians get the exceptions-first My Ward instead. Same first-isolate rule, n ≥ 30
 * and fallbacks as everywhere, and each cell's details compare with Finland (DATA-08).
 */
export function Explore() {
  const { meta, asOf, role } = useApp();
  const [f, setF] = useLocalStorage<ExploreState>("aei.explore", INITIAL);
  const set = (patch: Partial<ExploreState>) => setF({ ...f, ...patch });
  const [selected, setSelected] = useState<{ organism: string; code: string; sub?: string } | null>(null);

  const isWard = meta.wards.some((w) => w.ward_code === f.location);
  const firstYear = Number(meta.data_start.slice(0, 4));
  const lastYear = Number(asOf.slice(0, 4));
  const years = Array.from({ length: lastYear - firstYear + 1 }, (_, i) => lastYear - i);
  const year = f.year && f.year >= firstYear && f.year <= lastYear ? f.year : lastYear;
  const start = f.start && f.start <= asOf ? f.start : daysBefore(asOf, 90);
  const end = f.end && f.end <= asOf && f.end >= start ? f.end : asOf;

  const query = {
    location: f.location,
    specimen: f.specimen,
    ward_type: isWard ? undefined : f.ward_type,
    home_area: f.home_area,
    sex: f.sex,
    age_band: f.age_band,
    hospital_acquired: f.hospital_acquired,
    year: f.period === "year" ? year : undefined,
    period_start: f.period === "custom" ? start : undefined,
    period_end: f.period === "custom" ? end : undefined,
    as_of: asOf,
  };
  const ab = useFetch((signal) => api.antibiogram(query, signal), [JSON.stringify(query), meta.data_version]);
  const data = ab.data ? narrow(ab.data, f.organism, f.antibiotic) : null;

  const organisms = meta.organisms;
  const antibiotics = meta.antibiotics.filter((a) => a.reported_for === "all" || a.reported_for === f.specimen);
  const active = [f.ward_type, f.home_area, f.organism, f.antibiotic, f.sex, f.age_band, f.hospital_acquired].filter(
    (v) => v !== undefined,
  ).length;
  const acquisition = f.hospital_acquired === undefined ? "any" : f.hospital_acquired ? "hospital" : "community";

  const row = selected && data?.organisms.find((o) => o.organism === selected.organism);
  const subRow =
    row && selected?.sub
      ? (() => {
          const s = row.split?.rows.find((r) => r.label === selected.sub);
          return s ? { ...row, organism: `${row.organism} · ${s.label}`, isolates: s.isolates, cells: s.cells } : undefined;
        })()
      : row;
  const cell = subRow && selected ? subRow.cells[selected.code] : null;
  const antibiotic = selected && data?.antibiotics.find((a) => a.code === selected.code);

  return (
    <>
      <section className="ward-head">
        <div>
          <p className="eyebrow">{ROLES[role.role].label}</p>
          <h1>Explore resistance</h1>
          <p className="ward-sub">
            Any place, organism, patient group and period · as of {fmtDate(asOf)}
          </p>
        </div>
      </section>

      <div className="filters explore-filters">
        <fieldset className="explore-group">
          <legend>Where</legend>
          <label className="field">
            <span className="field-label">Location</span>
            <select value={f.location} onChange={(e) => set({ location: e.target.value })}>
              <optgroup label="Combined">
                {meta.locations.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </optgroup>
              <optgroup label="Hospital wards">
                {meta.wards
                  .filter((w) => w.institution === "hospital")
                  .map((w) => (
                    <option key={w.ward_code} value={w.ward_code}>
                      {w.ward_en} ({w.ward_code})
                    </option>
                  ))}
              </optgroup>
              <optgroup label="Health centres">
                {meta.wards
                  .filter((w) => w.institution === "primary_care")
                  .map((w) => (
                    <option key={w.ward_code} value={w.ward_code}>
                      {w.ward_en} ({w.ward_code})
                    </option>
                  ))}
              </optgroup>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Ward type</span>
            <select
              value={isWard ? "" : (f.ward_type ?? "")}
              disabled={isWard}
              title={isWard ? "A single ward is either in- or outpatient" : undefined}
              onChange={(e) => set({ ward_type: (e.target.value || undefined) as ExploreState["ward_type"] })}
            >
              <option value="">In- and outpatient</option>
              <option value="in">Inpatient wards</option>
              <option value="out">Outpatient (ED, health centres)</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Home area</span>
            <select value={f.home_area ?? ""} onChange={(e) => set({ home_area: e.target.value || undefined })}>
              <option value="">All areas</option>
              {meta.home_areas.map((h) => (
                <option key={h} value={h}>
                  {h}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <fieldset className="explore-group">
          <legend>What</legend>
          <div className="field">
            <span className="field-label">Specimen</span>
            <Segmented
              label="Specimen"
              value={f.specimen}
              onChange={(v) => set({ specimen: v, antibiotic: undefined })}
              options={meta.specimens.map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }))}
            />
          </div>
          <label className="field">
            <span className="field-label">Organism</span>
            <select value={f.organism ?? ""} onChange={(e) => set({ organism: e.target.value || undefined })}>
              <option value="">All organisms</option>
              {organisms.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Antibiotic</span>
            <select value={f.antibiotic ?? ""} onChange={(e) => set({ antibiotic: e.target.value || undefined })}>
              <option value="">All antibiotics</option>
              {antibiotics.map((a) => (
                <option key={a.code} value={a.code}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <fieldset className="explore-group">
          <legend>Who</legend>
          <div className="field">
            <span className="field-label">Sex</span>
            <Segmented
              label="Sex"
              value={f.sex ?? "any"}
              onChange={(v) => set({ sex: v === "any" ? undefined : v })}
              options={[
                { value: "any", label: "All" },
                { value: "F", label: "Women" },
                { value: "M", label: "Men" },
              ]}
            />
          </div>
          <label className="field">
            <span className="field-label">Age</span>
            <select value={f.age_band ?? ""} onChange={(e) => set({ age_band: e.target.value || undefined })}>
              <option value="">All ages</option>
              {meta.age_bands.map((b) => (
                <option key={b} value={b}>
                  {b} years
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Onset</span>
            <select
              value={acquisition}
              onChange={(e) =>
                set({ hospital_acquired: e.target.value === "any" ? undefined : e.target.value === "hospital" })
              }
            >
              <option value="any">Any onset</option>
              <option value="hospital">Hospital-acquired (day 3+)</option>
              <option value="community">Community / early</option>
            </select>
          </label>
        </fieldset>

        <fieldset className="explore-group">
          <legend>When</legend>
          <div className="field">
            <span className="field-label">Period</span>
            <Segmented
              label="Period"
              value={f.period}
              onChange={(v) => set({ period: v })}
              options={[
                { value: "rolling", label: "4 weeks + 12 months" },
                { value: "year", label: "Calendar year" },
                { value: "custom", label: "Custom" },
              ]}
            />
          </div>
          {f.period === "year" && (
            <label className="field">
              <span className="field-label">Year</span>
              <select value={year} onChange={(e) => set({ year: Number(e.target.value) })}>
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                    {y === lastYear ? " (so far)" : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          {f.period === "custom" && (
            <>
              <label className="field">
                <span className="field-label">From</span>
                <input
                  type="date"
                  value={start}
                  min={meta.data_start}
                  max={end}
                  onChange={(e) => e.target.value && set({ start: e.target.value })}
                />
              </label>
              <label className="field">
                <span className="field-label">To</span>
                <input
                  type="date"
                  value={end}
                  min={start}
                  max={asOf}
                  onChange={(e) => e.target.value && set({ end: e.target.value })}
                />
              </label>
            </>
          )}
        </fieldset>
        {(active > 0 || f.period !== "rolling") && (
          <button type="button" className="link-btn" onClick={() => setF({ ...INITIAL, location: f.location, specimen: f.specimen })}>
            Clear filters
          </button>
        )}
      </div>

      {ab.error && <p className="error">Could not load: {ab.error}</p>}
      {data && (
        <>
          <p className="explore-summary small">
            <strong>{data.scope.label}</strong> · {f.specimen} cultures
            {f.ward_type && !isWard ? (f.ward_type === "in" ? " · inpatient wards" : " · outpatient") : ""}
            {f.home_area ? ` · home area ${f.home_area}` : ""}
            {f.sex ? (f.sex === "F" ? " · women" : " · men") : ""}
            {f.age_band ? ` · ${f.age_band} years` : ""}
            {f.hospital_acquired !== undefined ? (f.hospital_acquired ? " · hospital-acquired" : " · community onset") : ""}
            {" · "}
            {data.period
              ? `${fmtDate(data.windows[0].start)} – ${fmtDate(data.windows[0].end)}`
              : `last 4 weeks and 12 months to ${fmtDate(asOf)}`}
            <span className="muted">
              {" "}
              · first isolate per patient, organism and specimen in each window; % only from {meta.thresholds.min_isolates}{" "}
              isolates, else counts or a broader level (H, P, A). Open a cell for the details and the Finland figure (
              {meta.national_source.label}).
            </span>
          </p>
          {data.organisms.length === 0 || data.antibiotics.length === 0 ? (
            <p className="muted">
              {f.organism && f.antibiotic
                ? `${f.organism} is not tested for this antibiotic in ${f.specimen} cultures.`
                : "Nothing to show for this combination."}
            </p>
          ) : (
            <motion.div className={`ab-card ${ab.loading ? "is-loading" : ""}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
              <Antibiogram data={data} onSelect={(organism, code, sub) => setSelected({ organism, code, sub })} />
            </motion.div>
          )}
          <Legend />
        </>
      )}

      <AnimatePresence>
        {data && subRow && cell && antibiotic && (
          <CellDetail
            key={`${subRow.organism}-${antibiotic.code}`}
            data={data}
            row={subRow}
            cell={cell}
            antibiotic={antibiotic}
            onClose={() => setSelected(null)}
          />
        )}
      </AnimatePresence>
    </>
  );
}

/** The organism and antibiotic filters narrow the table's rows and columns. */
function narrow(data: AntibiogramData, organism?: string, antibiotic?: string): AntibiogramData {
  const antibiotics = antibiotic ? data.antibiotics.filter((a) => a.code === antibiotic) : data.antibiotics;
  let organisms = organism ? data.organisms.filter((o) => o.organism === organism) : data.organisms;
  if (antibiotic) organisms = organisms.filter((o) => o.cells[antibiotic] != null);
  return { ...data, antibiotics, organisms };
}
