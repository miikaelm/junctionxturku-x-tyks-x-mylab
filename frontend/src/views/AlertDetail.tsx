import { useState } from "react";
import { api, type AlertDetail, type Estimate, type TriageStatus } from "../api/client";
import { fmtP, SeverityPill, TRIAGE_TEXT, TriagePill } from "../components/AlertBits";
import { BarChart } from "../components/BarChart";
import { fmtDate, shortOrganism } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { ROLES } from "../lib/roles";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";

/** V4 Alert detail / outbreak investigation: why it fired, timeline, cases, triage. */
export function AlertDetailView({ id }: { id: string }) {
  const { asOf, alertsVersion, meta, role } = useApp();
  const patientLevel = ROLES[role.role].patientLevel;
  const { data, error, loading } = useFetch(
    (signal) => api.alert(id, asOf, signal),
    [id, asOf, alertsVersion, meta.data_version],
  );

  return (
    <>
      <p className="back">
        <a href={href({ view: "alerts" })}>← All alerts</a>
      </p>
      {error && (
        <p className="error">
          {error.startsWith("404")
            ? `This alert had not fired yet as of ${fmtDate(asOf)}. Move the time cursor forward.`
            : `Could not load the alert: ${error}`}
        </p>
      )}
      {data && (
        <div className={loading ? "is-loading" : ""}>
          <section className="ward-head">
            <div>
              <p className="eyebrow">
                {data.type_label} · {data.wards.length > 1 ? data.wards.join(", ") : `${data.ward} ${data.ward_en}`}
              </p>
              <h1 className="alert-title">{data.title}</h1>
              <p className="ward-sub">
                <SeverityPill severity={data.severity} /> First seen {fmtDate(data.first_seen)} · last
                signal {fmtDate(data.last_seen)} ·{" "}
                {data.state === "active" ? "active" : `resolved ${fmtDate(data.resolved_on!)}`} ·{" "}
                <TriagePill alert={data} />
              </p>
              <p className="ward-sub muted small">
                {data.detection_days > 0
                  ? `Detected ${data.detection_days} day${data.detection_days > 1 ? "s" : ""} after ${data.type === "data_gap" ? "the gap began" : "the first case it counted"} (${fmtDate(data.onset)}).`
                  : "Detected on the day of the case."}
              </p>
            </div>
          </section>

          <div className="detail-grid">
            <section className="card pad">
              <h2>Why this alert fired</h2>
              <Why alert={data} />
              <p className="muted small method">Method: {data.evidence.method}</p>
            </section>
            <TriagePanel alert={data} />
          </div>

          {data.similarity && <SimilarityCard s={data.similarity} />}

          <section className="card pad">
            <BarChart timeline={data.timeline} />
          </section>

          {data.cases.length > 0 && (
            <section className="card pad">
              <h2>
                {data.type === "carrier" ? "Positive results behind the carrier flag" : "Cases"}{" "}
                <span className="muted">({data.cases.length})</span>
              </h2>
              {patientLevel ? (
                <CaseTable alert={data} />
              ) : (
                <p className="muted">
                  {data.cases.length} case{data.cases.length > 1 ? "s" : ""},{" "}
                  {data.cases.filter((c) => c.hospital_acquired).length} hospital-acquired. The patient-level line list
                  is for infection control and the lab (switch role to see it).
                </p>
              )}
            </section>
          )}

          {data.followup && data.followup.wards.length > 0 && (
            <FollowupCard alert={data} patientLevel={patientLevel} />
          )}

          {data.history.length > 1 && (
            <section className="card pad">
              <details>
                <summary>
                  <strong>Signal history</strong> <span className="muted">({data.history.length} evaluations that fired)</span>
                </summary>
                <ul className="history">
                  {data.history.map((h) => (
                    <li key={h.day}>
                      <span className="mono">{h.day}</span> {h.title}
                      {h.q_value !== undefined && <span className="muted"> · q {fmtP(h.q_value)}</span>}
                    </li>
                  ))}
                </ul>
              </details>
            </section>
          )}
        </div>
      )}
    </>
  );
}

function est(e: Estimate) {
  return `${e.pct} % (${e.r}/${e.n}, 95 % CI ${e.ci_low}–${e.ci_high} %)`;
}

/** Plain-language explanation of the evidence (ANOM-06), per alert type. */
function Why({ alert }: { alert: AlertDetail }) {
  const { role } = useApp();
  // Evidence fields differ per alert type (see the detectors' docstrings).
  const ev = alert.evidence as Record<string, any>;
  const win = ev.window ? `${fmtDate(ev.window.start)} – ${fmtDate(ev.window.end)}` : "";
  switch (alert.type) {
    case "sentinel":
      return (
        <dl className="facts">
          <dt>Finding</dt>
          <dd>{(ev.reasons as string[]).join("; ")}</dd>
          <dt>Organism</dt>
          <dd>
            {ev.organism} ({ev.specimen}), patient <span className="mono">{ev.patient_id}</span>
          </dd>
          <dt>Rule</dt>
          <dd>One case is enough: these are rare and need action (isolation, screening of contacts).</dd>
          {ev.seen_note && (
            <>
              <dt>On this ward</dt>
              <dd>{ev.seen_note}</dd>
            </>
          )}
        </dl>
      );
    case "cluster":
      return (
        <dl className="facts">
          <dt>Observed</dt>
          <dd>
            <strong>{ev.observed}</strong> new {ev.phenotype} cases in {win}
          </dd>
          <dt>Expected</dt>
          <dd>
            {ev.expected} (from {ev.baseline.cases} cases in the {ev.baseline.days} days before)
            {ev.ratio ? ` · ${ev.ratio}× the usual rate` : ""}
          </dd>
          <dt>Hospital-acquired</dt>
          <dd>
            {ev.hospital_acquired} of {ev.observed} sampled on hospital day 3 or later
            {ev.hospital_acquired * 2 >= ev.observed ? " – suggests spread on the ward" : ""}
          </dd>
          <dt>Organisms</dt>
          <dd>
            {Object.entries(ev.organisms as Record<string, number>)
              .map(([o, c]) => `${shortOrganism(o)} ${c}`)
              .join(", ")}
          </dd>
          <dt>Significance</dt>
          <dd>
            p {fmtP(ev.p_value)}, after false-discovery correction q {fmtP(ev.q_value)}
          </dd>
        </dl>
      );
    case "rate_shift":
      return (
        <>
          <p>
            Resistance of <strong>{ev.organism}</strong> ({ev.specimen}) on {alert.ward} in the last 4 weeks ({win})
            compared with the 12 months before ({fmtDate(ev.baseline.start)} – {fmtDate(ev.baseline.end)}), first isolates
            only:
          </p>
          <div className="table-scroll">
            <table className="table compact">
              <thead>
                <tr>
                  <th>Antibiotic</th>
                  <th>Last 4 weeks</th>
                  <th>12 months before</th>
                  <th>Change</th>
                  <th>q</th>
                </tr>
              </thead>
              <tbody>
                {(ev.shifts as any[]).map((s) => (
                  <tr key={s.antibiotic_code}>
                    <td>
                      <span className="mono">{s.antibiotic_code}</span> {s.antibiotic}
                    </td>
                    <td>{est(s.observed)}</td>
                    <td>{est(s.expected)}</td>
                    <td className="mono">+{s.increase_pp} pp</td>
                    <td className="mono">{fmtP(s.q_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      );
    case "novelty":
      return (
        <dl className="facts">
          <dt>Finding</dt>
          <dd>
            {alert.subject} in {ev.organism} ({ev.specimen})
          </dd>
          <dt>Last seen on this ward</dt>
          <dd>
            {ev.first_ever
              ? `Never since records began (${ev.gap_days} days of data)`
              : `${fmtDate(ev.previous)}, ${ev.gap_days} days earlier`}
          </dd>
          <dt>Rule</dt>
          <dd>Alert when not seen on the ward for at least {ev.min_gap_days} days. Fires on the first case, before any cluster statistics can.</dd>
        </dl>
      );
    case "carrier":
      return (
        <dl className="facts">
          <dt>Patient</dt>
          <dd>
            {ROLES[role.role].patientLevel ? (
              <a href={href({ view: "patient", id: ev.patient_id })} className="mono">
                {ev.patient_id}
              </a>
            ) : (
              <span className="mono">{ev.patient_id}</span>
            )}{" "}
            sampled here ({ev.specimen}
            {ev.inpatient ? `, admitted ${fmtDate(ev.admission_date)}` : ", outpatient"})
          </dd>
          <dt>Known carrier of</dt>
          <dd>
            {(ev.flags as any[]).map((f) => (
              <span key={f.phenotype} className="block">
                <strong>{f.phenotype}</strong> ({f.organisms.map(shortOrganism).join(", ")}): first positive{" "}
                {fmtDate(f.first_positive)} on {f.first_ward}
                {f.positives > 1 && `, ${f.positives} positives, last ${fmtDate(f.last_positive)} on ${f.last_ward}`}
              </span>
            ))}
          </dd>
          {ev.previous_sample && (
            <>
              <dt>Seen before on</dt>
              <dd>
                {ev.previous_sample.ward}, {fmtDate(ev.previous_sample.date)} (from sample dates; no transfer records)
              </dd>
            </>
          )}
          <dt>Action</dt>
          <dd>Contact precautions per the local guideline, from the sample day, before the culture result.</dd>
          <dt>Rule</dt>
          <dd>
            Any new sample of a known carrier on a hospital ward that hasn't sampled them in the last {ev.revisit_days}{" "}
            days.
          </dd>
        </dl>
      );
    case "multi_ward":
      return (
        <dl className="facts">
          <dt>Strain type</dt>
          <dd>
            {ev.phenotype} {ev.organism}, {ev.profile_label} (urine-only agents left out so specimens compare)
          </dd>
          <dt>Wards</dt>
          <dd>
            {Object.entries(ev.by_ward as Record<string, number>)
              .map(([w, n]) => `${w} ${n}`)
              .join(", ")}{" "}
            in {win}
          </dd>
          <dt>Observed</dt>
          <dd>
            <strong>{ev.observed}</strong> cases vs {ev.expected} expected hospital-wide (from {ev.baseline.cases} in the{" "}
            {ev.baseline.days} days before)
          </dd>
          <dt>Outside {ev.outside_main.ward}</dt>
          <dd>
            {ev.outside_main.observed} cases vs {ev.outside_main.expected} expected (p {fmtP(ev.p_outside)}): the excess
            is not confined to one ward
          </dd>
          <dt>Significance</dt>
          <dd>
            p {fmtP(ev.p_value)}, after false-discovery correction q {fmtP(ev.q_value)}
          </dd>
          <dt>Caution</dt>
          <dd>
            Co-occurrence, not proof of transmission: the data has no transfer records, so the direction of spread is
            unknown. {ev.patients_on_several_wards > 0 && `${ev.patients_on_several_wards} patient(s) were sampled on several of these wards.`}
          </dd>
        </dl>
      );
    case "data_gap":
      return (
        <dl className="facts">
          <dt>Last sample</dt>
          <dd>
            {fmtDate(ev.last_sample)} ({ev.silent_days} silent day{ev.silent_days === 1 ? "" : "s"})
          </dd>
          <dt>Usual volume</dt>
          <dd>{ev.samples_per_day} samples per day</dd>
          <dt>Last 7 days</dt>
          <dd>
            {ev.observed} samples, expected ~{ev.expected}
          </dd>
          <dt>Meaning</dt>
          <dd>
            Results for this ward are incomplete. Low resistance numbers here may mean <em>no data</em>, not{" "}
            <em>no resistance</em>.
          </dd>
        </dl>
      );
  }
}

function TriagePanel({ alert }: { alert: AlertDetail }) {
  const { meta, asOf, refreshAlerts } = useApp();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const act = async (status: TriageStatus) => {
    setBusy(true);
    setErr(null);
    try {
      await api.triage(alert.id, status, asOf, note);
      setNote("");
      refreshAlerts();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card pad">
      <h2>Triage</h2>
      <p>
        Status: <TriagePill alert={alert} />
      </p>
      <label className="field">
        <span className="field-label">Note (optional)</span>
        <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. contact precautions started" />
      </label>
      <div className="triage-actions">
        {meta.triage_statuses
          .filter((s) => s !== alert.triage.status)
          .map((s) => (
            <button type="button" key={s} disabled={busy} onClick={() => act(s)} className={`btn btn-${s}`}>
              {s === "new" ? "Reopen" : TRIAGE_TEXT[s]}
            </button>
          ))}
      </div>
      {err && <p className="error">{err}</p>}
      {alert.triage_history.length > 0 && (
        <ul className="history">
          {alert.triage_history.map((h) => (
            <li key={h.at + h.status}>
              <span className="mono">{h.as_of}</span> {TRIAGE_TEXT[h.status]}
              {h.note && <span className="muted"> – {h.note}</span>}
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">Actions are recorded at the current as-of date ({fmtDate(asOf)}).</p>
    </section>
  );
}

function CaseTable({ alert }: { alert: AlertDetail }) {
  const highlight = alert.type === "rate_shift" ? (alert.evidence.antibiotic_code as string) : null;
  const profiles = alert.similarity !== null;
  const dominant = alert.similarity?.dominant.key;
  return (
    <div className="table-scroll">
      <table className="table compact">
        <thead>
          <tr>
            <th>Date</th>
            <th>Patient</th>
            <th>Sex / age</th>
            <th>Ward</th>
            <th>Specimen</th>
            <th>Organism</th>
            <th>Day of stay</th>
            <th>Resistant to</th>
            {profiles && <th>Profile</th>}
          </tr>
        </thead>
        <tbody>
          {alert.cases.map((c) => (
            <tr key={c.isolate_id} className={c.highlight ? "is-hit" : ""}>
              <td className="mono nowrap">{c.date}</td>
              <td className="mono">
                <a href={href({ view: "patient", id: c.patient_id })}>{c.patient_id}</a>
              </td>
              <td>
                {c.sex} {c.age}
              </td>
              <td className="mono">{c.ward}</td>
              <td>{c.specimen}</td>
              <td>
                {shortOrganism(c.organism)}
                {c.phenotypes.map((p) => (
                  <span key={p} className="tag tag-muted">
                    {p}
                  </span>
                ))}
              </td>
              <td>
                {c.days_since_admission === null
                  ? "outpatient"
                  : `day ${c.days_since_admission + 1}${c.hospital_acquired ? " (HA)" : ""}`}
              </td>
              <td className="mono small">
                {c.resistant.length
                  ? c.resistant.map((r) => (
                      <span key={r} className={r === highlight ? "hit" : ""}>
                        {r}{" "}
                      </span>
                    ))
                  : "–"}
              </td>
              {profiles && (
                <td className={`small ${c.profile === dominant ? "profile-main" : ""}`}>
                  {c.profile === undefined ? "–" : c.profile === dominant ? "main profile" : "differs"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small table-foot">
        {highlight && <>Highlighted: resistant to {highlight}. </>}HA = hospital-acquired (sampled on hospital day 3 or
        later). Patient-level data: for infection control and lab use.
      </p>
    </div>
  );
}

/** How alike the cases' resistance profiles are, against the background (ANOM-05). */
function SimilarityCard({ s }: { s: NonNullable<AlertDetail["similarity"]> }) {
  const tone = s.verdict === "single_strain" ? "bad" : s.verdict === "common_profile" ? "warn" : "none";
  return (
    <section className="card pad">
      <h2>Same strain? Resistance profiles of the cases</h2>
      <p className={`verdict verdict-${tone}`}>{s.text}</p>
      <div className="table-scroll">
        <table className="table compact">
          <thead>
            <tr>
              <th>Profile ({shortOrganism(s.organism)})</th>
              <th>Cases</th>
            </tr>
          </thead>
          <tbody>
            {s.groups.map((g) => (
              <tr key={g.key} className={g.key === s.dominant.key ? "row-strong" : ""}>
                <td>{g.label}</td>
                <td className="mono">{g.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        {s.matching} of {s.cases} match the main profile on every agent both were tested for
        {s.mean_agreement !== null && `; on average two cases agree on ${Math.round(100 * s.mean_agreement)} % of shared agents`}.
        {s.background.share !== null
          ? ` Background: ${s.background.matching} of ${s.background.isolates} similar isolates elsewhere (${fmtDate(s.background.start)} – ${fmtDate(s.background.end)}) had it; p ${fmtP(s.p_value ?? undefined)}.`
          : " Too few similar isolates elsewhere to say how unusual the profile is."}
        {s.other_organisms > 0 && ` ${s.other_organisms} case(s) of other organisms not compared.`}
      </p>
      <p className="muted small method">Method: {s.method}</p>
    </section>
  );
}

/** Where the patients behind the alert were sampled next (PAT-03), as a follow-up list. */
function FollowupCard({ alert, patientLevel }: { alert: AlertDetail; patientLevel: boolean }) {
  const f = alert.followup!;
  const seen = f.patients.length;
  return (
    <section className="card pad">
      <h2>
        Where they were sampled next <span className="muted">(within {f.days} days, other wards)</span>
      </h2>
      <p>
        {seen} of {f.case_patients} patient{f.case_patients > 1 ? "s" : ""} turned up on other wards afterwards:{" "}
        {f.wards.map((w) => `${w.ward} (${w.patients}, from ${fmtDate(w.first)})`).join(", ")}.
      </p>
      {patientLevel ? (
        <details className="small">
          <summary>Follow-up list ({seen} patients)</summary>
          <table className="table compact">
            <thead>
              <tr>
                <th>Patient</th>
                <th>Case</th>
                <th>Then sampled on</th>
              </tr>
            </thead>
            <tbody>
              {f.patients.map((p) => (
                <tr key={p.patient_id}>
                  <td className="mono">
                    <a href={href({ view: "patient", id: p.patient_id })}>{p.patient_id}</a>
                  </td>
                  <td className="nowrap">
                    {p.case_ward}, {p.case_date}
                  </td>
                  <td>{p.seen.map((s) => `${s.ward} ${s.date}`).join(" → ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}
      <p className="muted small">
        From sample dates only: there are no admission or transfer records, so this shows where patients were seen, not
        how they moved or whether they carried the strain there.{" "}
        {alert.type !== "carrier" && <a href={href({ view: "spread" })}>Open the spread view →</a>}
      </p>
    </section>
  );
}
