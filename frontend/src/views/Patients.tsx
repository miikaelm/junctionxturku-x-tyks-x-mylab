import { useState } from "react";
import { api } from "../api/client";
import { AlertList } from "../components/AlertBits";
import { fmtDate, shortOrganism } from "../lib/format";
import { useFetch, useLocalStorage } from "../lib/hooks";
import { ROLES } from "../lib/roles";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";

const PERIODS = [
  { days: 28, label: "Last 4 weeks" },
  { days: 91, label: "Last 13 weeks" },
  { days: 365, label: "Last 12 months" },
  { days: 0, label: "All" },
];

function Restricted() {
  return <p className="empty">Patient-level data is for infection control and the lab (switch role to see it).</p>;
}

/** Carrier registry (PAT-01): every patient with an MRSA / ESBL / VRE / CPE result, newest first. */
export function Patients() {
  const { meta, asOf, role } = useApp();
  const [phenotype, setPhenotype] = useState("");
  const [location, setLocation] = useState("all");
  const [days, setDays] = useLocalStorage("aei.carriers.days", 91);
  const [search, setSearch] = useState("");
  const { data, error, loading } = useFetch(
    (signal) =>
      api.carriers(
        { as_of: asOf, phenotype: phenotype || undefined, location, days: days || undefined, limit: 300 },
        signal,
      ),
    [asOf, phenotype, location, days, meta.data_version],
  );
  if (!ROLES[role.role].patientLevel) return <Restricted />;

  return (
    <>
      <section className="ward-head">
        <div>
          <p className="eyebrow">Infection control</p>
          <h1>Known carriers</h1>
          <p className="ward-sub">
            Derived automatically from lab results · {data ? `${data.total} flags` : "…"} · as of {fmtDate(asOf)}
          </p>
        </div>
        <form
          className="patient-search"
          onSubmit={(e) => {
            e.preventDefault();
            if (search.trim()) window.location.hash = href({ view: "patient", id: search.trim().toUpperCase() });
          }}
        >
          <label className="field">
            <span className="field-label">Find a patient</span>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="P001234" />
          </label>
          <button type="submit" className="btn">
            Open
          </button>
        </form>
      </section>

      <div className="filters">
        <div className="filters-patient">
          <label className="field">
            <span className="field-label">Phenotype</span>
            <select value={phenotype} onChange={(e) => setPhenotype(e.target.value)}>
              <option value="">All</option>
              {meta.phenotypes.map((p) => (
                <option key={p} value={p}>
                  {p}
                  {data?.by_phenotype[p] !== undefined && !phenotype ? ` (${data.by_phenotype[p]})` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Positive on</span>
            <select value={location} onChange={(e) => setLocation(e.target.value)}>
              {meta.locations.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
              {meta.wards.map((w) => (
                <option key={w.ward_code} value={w.ward_code}>
                  {w.ward_code} · {w.ward_en}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">First flagged</span>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {PERIODS.map((p) => (
                <option key={p.days} value={p.days}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error && <p className="error">Could not load carriers: {error}</p>}
      {data && (
        <div className={`card ${loading ? "is-loading" : ""}`}>
          {data.carriers.length === 0 ? (
            <p className="empty">No carrier flags for this selection.</p>
          ) : (
            <div className="table-scroll">
              <table className="table compact">
                <thead>
                  <tr>
                    <th>Patient</th>
                    <th>Phenotype</th>
                    <th>Organism</th>
                    <th>First positive</th>
                    <th>Positives</th>
                    <th>Last positive</th>
                    <th>Wards</th>
                  </tr>
                </thead>
                <tbody>
                  {data.carriers.map((c) => (
                    <tr key={`${c.patient_id}-${c.phenotype}`}>
                      <td className="mono">
                        <a href={href({ view: "patient", id: c.patient_id })}>{c.patient_id}</a>
                      </td>
                      <td>
                        <span className={`tag ${["CPE", "VRE"].includes(c.phenotype) ? "tag-bad" : ""}`}>{c.phenotype}</span>
                      </td>
                      <td>{c.organisms.map(shortOrganism).join(", ")}</td>
                      <td className="nowrap">
                        {fmtDate(c.first_positive)}, {c.first_ward}
                      </td>
                      <td className="mono">{c.positives}</td>
                      <td className="nowrap">
                        {c.positives > 1 ? `${fmtDate(c.last_positive)}, ${c.last_ward}` : "–"}
                      </td>
                      <td className="mono small">{c.wards.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.total > data.carriers.length && (
            <p className="muted small table-foot">Showing the newest {data.carriers.length} of {data.total}.</p>
          )}
        </div>
      )}
      <p className="muted small note">
        A patient is flagged from the day of their first positive result and stays flagged: clearing a flag needs
        negative screening results, which this data doesn't have. When a flagged patient gets a new sample on a hospital
        ward, that ward gets a "known carrier sampled" alert.
      </p>
    </>
  );
}

/** One patient: carrier flags, alerts they are part of, and every sample up to as-of. */
export function PatientView({ id }: { id: string }) {
  const { asOf, role, meta, alertsVersion } = useApp();
  const { data, error } = useFetch((signal) => api.patient(id, asOf, signal), [id, asOf, meta.data_version, alertsVersion]);
  if (!ROLES[role.role].patientLevel) return <Restricted />;

  return (
    <>
      {error && <p className="error">{error.startsWith("404") ? `No samples for ${id} up to ${fmtDate(asOf)}.` : error}</p>}
      {data && (
        <>
          <section className="ward-head">
            <div>
              <p className="eyebrow">Patient</p>
              <h1 className="mono">{data.patient_id}</h1>
              <p className="ward-sub">
                {data.sex === "F" ? "Woman" : "Man"}, {data.age} · home area {data.home_area} · last sample{" "}
                {fmtDate(data.last_sample)} on {data.last_ward} ·{" "}
                <a href={href({ view: "ehr", id: data.patient_id })}>open in the mock patient record</a>
              </p>
            </div>
          </section>
          {data.flags.length > 0 ? (
            <div className="flag-list">
              {data.flags.map((f) => (
                <div key={f.phenotype} className={`flag ${["CPE", "VRE"].includes(f.phenotype) ? "is-critical" : ""}`}>
                  <strong>Known {f.phenotype} carrier</strong> · {f.organisms.join(", ")} · first positive{" "}
                  {fmtDate(f.first_positive)} on {f.first_ward}
                  {f.positives > 1 && ` · ${f.positives} positives, last ${fmtDate(f.last_positive)} on ${f.last_ward}`}
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No carrier flags as of {fmtDate(asOf)}.</p>
          )}
          {data.alerts.length > 0 && (
            <section className="card pad">
              <h2>Active alerts involving this patient</h2>
              <AlertList alerts={data.alerts} />
            </section>
          )}
          <section className="card pad">
            <h2>
              Samples <span className="muted">({data.samples.length}, newest first)</span>
            </h2>
            <div className="table-scroll">
              <table className="table compact">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Ward</th>
                    <th>Specimen</th>
                    <th>Result</th>
                    <th>Findings</th>
                  </tr>
                </thead>
                <tbody>
                  {data.samples.map((s) => (
                    <tr key={s.culture_id}>
                      <td className="mono nowrap">{s.date}</td>
                      <td className="mono">
                        {s.ward}
                        {s.admission_date && <span className="muted small"> (adm. {s.admission_date})</span>}
                      </td>
                      <td>{s.specimen}</td>
                      <td>{s.result.replace("_", " ")}</td>
                      <td>
                        {s.isolates.map((i) => (
                          <span key={i.isolate_id} className="block">
                            {shortOrganism(i.organism)}
                            {i.phenotypes.map((p) => (
                              <span key={p} className="tag tag-bad">
                                {p}
                              </span>
                            ))}
                            {i.resistant.length > 0 && <span className="mono small muted"> R: {i.resistant.join(" ")}</span>}
                          </span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
