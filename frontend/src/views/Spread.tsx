import { useState } from "react";
import { api, type Spread as SpreadData } from "../api/client";
import { fmtDate, shortOrganism } from "../lib/format";
import { useFetch, useLocalStorage } from "../lib/hooks";
import { ROLES } from "../lib/roles";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";

const PERIODS = [
  { days: 56, label: "8 weeks" },
  { days: 91, label: "13 weeks" },
  { days: 182, label: "26 weeks" },
  { days: 365, label: "1 year" },
  { days: 730, label: "2 years" },
];

/** V10 Spread / footprint (PAT-03, ANOM-09): one phenotype across wards over time, by profile. */
export function Spread() {
  const { meta, asOf, role } = useApp();
  const [phenotype, setPhenotype] = useLocalStorage("aei.spread.phenotype", "ESBL");
  const [days, setDays] = useLocalStorage("aei.spread.days", 182);
  const [organism, setOrganism] = useState("");
  const [focus, setFocus] = useState<string | null>(null);
  const [paths, setPaths] = useState(false);
  const { data, error, loading } = useFetch(
    (signal) => api.spread({ phenotype, organism: organism || undefined, days, as_of: asOf }, signal),
    [phenotype, organism, days, asOf, meta.data_version],
  );

  if (!ROLES[role.role].patientLevel) {
    return <p className="empty">The spread view shows patient-level data: it is for infection control and the lab.</p>;
  }
  const organisms = [...new Set((data?.profiles ?? []).map((p) => p.organism))];

  return (
    <>
      <section className="ward-head">
        <div>
          <p className="eyebrow">Infection control</p>
          <h1>Spread across wards</h1>
          <p className="ward-sub">
            New {phenotype} cases by ward, coloured by resistance profile · {data ? `${fmtDate(data.start)} – ` : ""}
            {fmtDate(asOf)}
          </p>
        </div>
      </section>

      <div className="filters">
        <div className="filters-patient">
          <label className="field">
            <span className="field-label">Phenotype</span>
            <select
              value={phenotype}
              onChange={(e) => {
                setPhenotype(e.target.value);
                setOrganism("");
                setFocus(null);
              }}
            >
              {meta.phenotypes.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Organism</span>
            <select value={organism} onChange={(e) => setOrganism(e.target.value)}>
              <option value="">All</option>
              {organisms.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Period</span>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {PERIODS.map((p) => (
                <option key={p.days} value={p.days}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="check">
            <input type="checkbox" checked={paths} onChange={(e) => setPaths(e.target.checked)} />
            Patient paths
          </label>
        </div>
      </div>

      {error && <p className="error">Could not load the spread view: {error}</p>}
      {data && (
        <div className={loading ? "is-loading" : ""}>
          <section className="card pad">
            {data.cases.length === 0 ? (
              <p className="empty">No new {phenotype} cases in this period.</p>
            ) : (
              <SpreadChart data={data} focus={focus} showPaths={paths} />
            )}
            <p className="muted small table-foot">
              One dot per new case (repeat positives within 90 days count once); colour = resistance profile. Patient paths
              (tick the box, or click a profile) join a case patient's samples on different wards (small rings: samples
              without this finding). Triangles
              mark cluster and multi-ward alerts. Inferred from sample dates: no transfer records, so no direction of
              spread is claimed.
            </p>
          </section>

          <div className="detail-grid">
            <section className="card pad">
              <h2>Resistance profiles</h2>
              <table className="table compact">
                <thead>
                  <tr>
                    <th />
                    <th>Profile</th>
                    <th>Cases</th>
                    <th>Wards</th>
                  </tr>
                </thead>
                <tbody>
                  {data.profiles.map((p) => (
                    <tr
                      key={p.id}
                      className={`row-click ${focus === p.id ? "row-strong" : ""}`}
                      onClick={() => setFocus(focus === p.id ? null : p.id)}
                    >
                      <td>
                        <span className={`swatch p${p.colour ?? "x"}`} />
                      </td>
                      <td>
                        {shortOrganism(p.organism)} · {p.label}
                      </td>
                      <td className="mono">{p.count}</td>
                      <td className={p.wards.length > 1 ? "strong" : ""}>{p.wards.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted small">Click a profile to highlight it. Common profiles are shared by unrelated strains.</p>
            </section>
            <section className="card pad">
              <h2>Alerts in this period</h2>
              {data.alerts.length === 0 ? (
                <p className="muted">No cluster or multi-ward alerts for {phenotype}.</p>
              ) : (
                <ul className="history">
                  {data.alerts.map((a) => (
                    <li key={a.id}>
                      <span className="mono">{a.first_seen}</span>{" "}
                      <a href={href({ view: "alert", id: a.id })}>
                        {a.type_label}: {a.title}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
              <p className="muted small">
                {data.paths.length} case patient{data.paths.length === 1 ? " was" : "s were"} sampled on more than one
                ward in the period.
              </p>
            </section>
          </div>
        </div>
      )}
    </>
  );
}

function SpreadChart({ data, focus, showPaths }: { data: SpreadData; focus: string | null; showPaths: boolean }) {
  const W = 900;
  const rowH = 30;
  const pad = { l: 64, r: 12, t: 16, b: 26 };
  const H = pad.t + rowH * data.wards.length + pad.b;
  const t0 = new Date(`${data.start}T00:00:00Z`).getTime();
  const t1 = new Date(`${data.as_of}T00:00:00Z`).getTime();
  const x = (iso: string) => pad.l + ((new Date(`${iso}T00:00:00Z`).getTime() - t0) / Math.max(1, t1 - t0)) * (W - pad.l - pad.r);
  const row = new Map(data.wards.map((w, i) => [w, i]));
  const y = (ward: string) => pad.t + rowH * (row.get(ward) ?? 0) + rowH / 2;
  const colour = new Map(data.profiles.map((p) => [p.id, p.colour]));
  // Paths of the highlighted profile's patients, or of every case patient when asked for.
  const caseKeys = new Set(data.cases.filter((c) => !focus || c.profile_id === focus).map((c) => c.patient_id));
  const ticks = 6;

  return (
    <div className="table-scroll">
      <svg viewBox={`0 0 ${W} ${H}`} className="spread-chart" role="img" aria-label="Cases by ward over time">
        {data.wards.map((w) => (
          <g key={w}>
            <line x1={pad.l} x2={W - pad.r} y1={y(w)} y2={y(w)} className="chart-grid" />
            <text x={pad.l - 8} y={y(w) + 4} textAnchor="end" className="chart-tick">
              {w}
            </text>
          </g>
        ))}
        {Array.from({ length: ticks + 1 }, (_, i) => {
          const iso = new Date(t0 + ((t1 - t0) * i) / ticks).toISOString().slice(0, 10);
          return (
            <text key={iso} x={x(iso)} y={H - 8} textAnchor={i === 0 ? "start" : i === ticks ? "end" : "middle"} className="chart-tick">
              {fmtDate(iso)}
            </text>
          );
        })}
        {(showPaths || focus) &&
          data.paths
            .filter((p) => caseKeys.has(p.patient_id))
            .map((p) => (
              <g key={p.patient_id} className="spread-path">
                <title>
                  {p.patient_id}: {p.samples.map((s) => `${s.ward} ${s.date}`).join(" → ")}
                </title>
                <polyline points={p.samples.map((s) => `${x(s.date)},${y(s.ward)}`).join(" ")} />
                {p.samples
                  .filter((s) => !s.case)
                  .map((s, i) => (
                    <circle key={i} cx={x(s.date)} cy={y(s.ward)} r={3} className="spread-sample" />
                  ))}
              </g>
            ))}
        {data.alerts.flatMap((a) =>
          a.wards
            .filter((w) => row.has(w))
            .map((w) => (
              <a key={`${a.id}-${w}`} href={href({ view: "alert", id: a.id })}>
                <title>
                  {a.type_label}: {a.title} ({a.first_seen})
                </title>
                <path
                  d={`M${x(a.first_seen)},${y(w) - 15} l5,-8 h-10 z`}
                  className={`spread-alert ${a.type === "multi_ward" ? "is-multi" : ""}`}
                />
              </a>
            )),
        )}
        {data.cases.map((c) => {
          const col = colour.get(c.profile_id);
          const faded = focus !== null && focus !== c.profile_id;
          return (
            <a key={c.isolate_id} href={href({ view: "patient", id: c.patient_id })}>
              <title>
                {c.date} · {c.ward} · {c.patient_id} · {c.organism} ({c.specimen})
                {c.hospital_acquired ? " · hospital-acquired" : ""} ·{" "}
                {data.profiles.find((p) => p.id === c.profile_id)?.label}
              </title>
              <circle
                cx={x(c.date)}
                cy={y(c.ward)}
                r={6}
                className={`spread-dot p${col ?? "x"} ${faded ? "is-faded" : ""} ${c.hospital_acquired ? "is-ha" : ""}`}
              />
            </a>
          );
        })}
      </svg>
    </div>
  );
}
