import { useState } from "react";
import { api, type Finding, type FindingKind, type ReviewStatus } from "../api/client";
import { fmtP } from "../components/AlertBits";
import { monthYear } from "../components/AvoidList";
import { fmtDate, shortOrganism } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";
import { Series } from "./Trends";

const ACTION: Record<ReviewStatus, string> = {
  new: "Reopen",
  under_review: "Start review",
  guideline_updated: "Guideline updated",
  accepted: "Accept: guideline unchanged",
};
const DONE: Record<ReviewStatus, string> = {
  new: "Reopened",
  under_review: "Review started",
  guideline_updated: "Guideline updated",
  accepted: "Accepted, guideline unchanged",
};

/**
 * Stewardship findings to review (ANOM-10): long-standing resistance has an owner and a status
 * instead of being an alert. Crossings and rises first; what has always been high is folded away.
 */
export function FindingsToReview() {
  const { asOf, meta } = useApp();
  const { data, error, loading } = useFetch((signal) => api.stewardship(asOf, signal), [asOf, meta.data_version]);
  if (error) return <p className="error">Could not load the findings: {error}</p>;
  if (!data) return <p className="muted">Collecting findings from every ward's avoid list…</p>;
  const of = (k: FindingKind) => data.findings.filter((f) => f.kind === k);
  const thr = data.threshold_pct;

  return (
    <div className={`findings ${loading ? "is-loading" : ""}`}>
      <section className="card pad">
        <h2>
          Crossed the {thr} % limit <span className="muted">({of("crossed").length})</span>
        </h2>
        <p className="muted small">
          A main organism of an infection became ≥ {thr} % resistant over 12 months, inside the data. These now show on
          clinicians' avoid lists: does the local guideline still fit?
        </p>
        <FindingRows rows={of("crossed")} empty="Nothing crossed the limit." />
      </section>
      <section className="card pad">
        <h2>
          Rising, still under {thr} % <span className="muted">({of("rising").length})</span>
        </h2>
        <p className="muted small">Significant upward trends over the quarters (ANOM-03): worth watching before they cross.</p>
        <FindingRows rows={of("rising")} empty="No significant upward trend under the limit." />
      </section>
      <details className="card pad findings-standing">
        <summary>
          <strong>Above {thr} % as far back as the data goes</strong> <span className="muted">({of("standing").length})</span>
          <span className="muted small"> · known background, e.g. ampicillin in E. coli</span>
        </summary>
        <FindingRows rows={of("standing")} empty="None." />
      </details>
    </div>
  );
}

function FindingRows({ rows, empty }: { rows: Finding[]; empty: string }) {
  if (rows.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className="finding-rows">
      {rows.map((f) => (
        <li key={f.id}>
          <a href={href({ view: "finding", id: f.id })} className="finding-row">
            <span className="finding-what">
              <strong>{cap(f.antibiotic)}</strong> · {shortOrganism(f.organism)} · {f.infections.join(", ") || f.specimen}
              <span className="muted"> · {f.location_label}</span>
            </span>
            <span className="finding-numbers mono">
              {Math.round(f.last_12m.pct ?? 0)} % <span className="muted">({f.last_12m.r}/{f.last_12m.n})</span>
            </span>
            <span className="finding-when muted small">
              {f.since && !f.since.at_least && `since ${monthYear(f.since.date)}`}
              {f.trend && ` ${f.trend.pp_per_year > 0 ? "+" : ""}${f.trend.pp_per_year} pp/yr`}
            </span>
            <ReviewChip status={f.review.status} label={f.review.label} />
          </a>
        </li>
      ))}
    </ul>
  );
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function ReviewChip({ status, label }: { status: ReviewStatus; label: string }) {
  return <span className={`review-chip review-${status}`}>{label}</span>;
}

/** One finding: what it is, why it is not an alert, its review, and the long-term series. */
export function FindingView({ id }: { id: string }) {
  const { asOf, meta, role } = useApp();
  const [version, setVersion] = useState(0);
  const { data, error, loading } = useFetch((signal) => api.finding(id, asOf, signal), [id, asOf, meta.data_version, version]);
  if (error) {
    return (
      <p className="error">
        {error.startsWith("404") ? `This was not a finding as of ${fmtDate(asOf)}: the resistance was under the limit then.` : error}
      </p>
    );
  }
  if (!data) return <p className="muted">Loading…</p>;
  const e = data.last_12m;
  const thr = meta.thresholds.empirical_pct;
  const kind = data.kind;

  return (
    <div className={loading ? "is-loading" : ""}>
      <section className="ward-head">
        <div>
          <p className="eyebrow">Stewardship finding · {kind === "crossed" ? "crossed the limit" : kind === "rising" ? "rising" : "long-standing"}</p>
          <h1>
            {cap(data.antibiotic)}: {shortOrganism(data.organism)} {Math.round(e.pct ?? 0)} % resistant
          </h1>
          <p className="ward-sub">
            {data.infections.join(", ") || data.specimen} · {data.location_label} · as of {fmtDate(data.as_of)}
          </p>
        </div>
      </section>

      <div className="detail-grid">
        <section className="card pad">
          <h2>What this is</h2>
          <p>
            {kind === "crossed" &&
              `Above the ${thr} % empirical-use limit since ${monthYear(data.since!.date)}: ${e.r} of ${e.n} first isolates of ${data.organism} resistant in the last 12 months (95 % interval ${e.ci_low}–${e.ci_high} %).`}
            {kind === "standing" &&
              `Above the ${thr} % limit for as long as the data goes back (since ${monthYear(data.since!.date)} or earlier): ${e.r} of ${e.n} first isolates resistant in the last 12 months (95 % interval ${e.ci_low}–${e.ci_high} %).`}
            {kind === "rising" &&
              `Still under the ${thr} % limit (${e.r} of ${e.n}, ${e.pct} % in the last 12 months), but rising significantly over the quarters.`}
          </p>
          {data.trend && (
            <p className="small">
              Trend {data.trend.pp_per_year > 0 ? "+" : ""}
              {data.trend.pp_per_year} percentage points a year over {data.trend.quarters} quarters (q {fmtP(data.trend.q_value ?? undefined)}).
            </p>
          )}
          {data.wards.length > 0 && (
            <p className="small">
              On the avoid list of:{" "}
              {data.wards.map((w, i) => (
                <span key={w}>
                  {i > 0 && ", "}
                  <a href={href({ view: "ward", id: w })}>{w}</a>
                </span>
              ))}
              {data.level !== "ward" && <span className="muted"> (their own numbers are too few, so they use {data.location_label})</span>}
            </p>
          )}
          {data.national && (
            <p className="small">
              Finland {data.national.year}
              {data.national.group ? ` (${data.national.group})` : ""}: <strong className="mono">{data.national.pct} %</strong> of{" "}
              {data.national.n.toLocaleString("en-GB")} {data.national.specimen_label} isolates (
              <a href={data.national.url} target="_blank" rel="noreferrer">
                {data.national.source}
              </a>
              ).{" "}
              {e.ci_low > data.national.pct
                ? "The local figure is above it (whole interval): a local problem, not just the national picture."
                : e.ci_high < data.national.pct
                  ? "The local figure is below it (whole interval)."
                  : "The local figure is within reach of it."}
            </p>
          )}
          <p className="muted small">
            Not an alert: long-standing resistance needs a guideline decision, not an investigation. Clinicians see it on
            their avoid list together with the review status set here.
          </p>
        </section>
        <ReviewPanel
          id={data.id}
          status={data.review.status}
          label={data.review.label}
          history={data.history}
          canReview={role.role === "lab"}
          onDone={() => setVersion((v) => v + 1)}
        />
      </div>

      <h2 className="section-title">Long-term series</h2>
      <Series sel={{ location: data.location, specimen: data.specimen, organism: data.organism, antibiotic: data.antibiotic_code }} />
    </div>
  );
}

function ReviewPanel({
  id,
  status,
  label,
  history,
  canReview,
  onDone,
}: {
  id: string;
  status: ReviewStatus;
  label: string;
  history: { status: ReviewStatus; as_of: string; note: string; at: string }[];
  canReview: boolean;
  onDone: () => void;
}) {
  const { asOf } = useApp();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const act = async (s: ReviewStatus) => {
    setBusy(true);
    setErr(null);
    try {
      await api.review(id, s, asOf, note);
      setNote("");
      onDone();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card pad">
      <h2>Review</h2>
      <p>
        Status: <ReviewChip status={status} label={label} />
      </p>
      {canReview ? (
        <>
          <label className="field">
            <span className="field-label">Note (optional)</span>
            <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. UTI guideline: trimethoprim no longer first choice on URO" />
          </label>
          <div className="triage-actions">
            {(Object.keys(ACTION) as ReviewStatus[])
              .filter((s) => s !== status && (s !== "new" || status !== "new"))
              .map((s) => (
                <button type="button" key={s} disabled={busy} onClick={() => act(s)} className="btn">
                  {ACTION[s]}
                </button>
              ))}
          </div>
          {err && <p className="error">{err}</p>}
          <p className="muted small">Recorded at the current as-of date ({fmtDate(asOf)}).</p>
        </>
      ) : (
        <p className="muted small">Lab and stewardship review findings; the status is shown to clinicians.</p>
      )}
      {history.length > 0 && (
        <ul className="history">
          {history.map((h) => (
            <li key={h.at + h.status}>
              <span className="mono">{h.as_of}</span> {DONE[h.status]}
              {h.note && <span className="muted"> – {h.note}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
