import { api, type AlertSummary, type Freshness, type Specimen } from "../api/client";
import { daysAgo, fmtDate } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { ROLES } from "../lib/roles";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";
import { AvoidList } from "./AvoidList";
import type { Filters } from "./FilterBar";

const INFECTION_OF = { urine: "uti", blood: "bloodstream", wound: "wound" } as const;

/**
 * The exceptions on a ward (UX-05): what not to use for this infection, and what is going on
 * here now. Everything normal stays further down the page.
 */
export function WardExceptions({
  location,
  specimen,
  filters,
  freshness,
}: {
  location: string;
  specimen: Specimen;
  filters: Filters;
  freshness: Freshness | null;
}) {
  const { meta } = useApp();
  const infection = INFECTION_OF[specimen];
  const label = meta.infections.find((i) => i.key === infection)?.label.toLowerCase() ?? infection;
  const who = [
    filters.sex === "F" ? "women" : filters.sex === "M" ? "men" : null,
    filters.age_band ? `${filters.age_band} years` : null,
    filters.hospital_acquired === true ? "hospital-acquired" : filters.hospital_acquired === false ? "community onset" : null,
  ].filter(Boolean);

  return (
    <div className="exceptions">
      <section className="card pad exc-card exc-avoid">
        <h2>
          Avoid for a {label}
          {who.length > 0 && <span className="muted"> · {who.join(", ")}</span>}
        </h2>
        <AvoidList location={location} infection={infection} filters={filters} />
      </section>
      <WardNow location={location} freshness={freshness} />
    </div>
  );
}

function WardNow({ location, freshness }: { location: string; freshness: Freshness | null }) {
  const { asOf, alertsVersion, meta, role } = useApp();
  const { data } = useFetch(
    (signal) => api.alerts({ as_of: asOf, location }, signal),
    [asOf, location, alertsVersion, meta.data_version],
  );
  const open = (data?.alerts ?? []).filter((a) => a.triage.status !== "dismissed");
  const signals = open.filter((a) => !a.routine && a.type !== "data_gap");
  const carriers = open.filter((a) => a.routine);
  const feed = freshness?.wards.find((w) => w.ward_code === location);
  const feedProblem = feed && feed.status !== "ok" ? feed : null;
  const action = (a: AlertSummary) => meta.alert_types.find((t) => t.key === a.type)?.action;
  const calm = data && signals.length === 0 && !feedProblem;

  return (
    <section className="card pad exc-card exc-now">
      <h2>On this ward now</h2>
      {!data && <p className="muted small">Checking alerts…</p>}
      {calm && <p className="avoid-none">Nothing unusual here.</p>}
      <ul className="now-list">
        {feedProblem && (
          <li className="now-item sev-line-medium">
            <strong>Lab data {feedProblem.status === "stale" ? "missing" : "delayed"}</strong>
            <span>
              Last sample {daysAgo(feedProblem.days_since_last)}: figures here may be out of date.
            </span>
          </li>
        )}
        {signals.map((a) => (
          <li key={a.id} className={`now-item sev-line-${a.severity}`}>
            <a href={href({ view: "alert", id: a.id })}>
              <strong>{a.type_label}</strong> <span className="now-since">since {fmtDate(a.first_seen)}</span>
              <span className="now-title">{a.title}</span>
            </a>
            {action(a) && <span className="now-action">{action(a)}</span>}
          </li>
        ))}
      </ul>
      {carriers.length > 0 && (
        <p className="muted small now-carriers">
          {carriers.length} known carrier{carriers.length > 1 ? "s" : ""} sampled here recently: contact precautions.{" "}
          {ROLES[role.role].patientLevel && <a href={href({ view: "patients" })}>Carriers →</a>}
        </p>
      )}
    </section>
  );
}
