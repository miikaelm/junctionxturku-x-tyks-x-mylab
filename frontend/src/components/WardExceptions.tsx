import { api, type Avoid, type AlertSummary, type Freshness, type Infection } from "../api/client";
import { daysAgo, fmtDate } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { ROLES } from "../lib/roles";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";
import { AvoidList } from "./AvoidList";
import type { Filters } from "./FilterBar";

export type InfectionFocus = Infection | "all";

/**
 * The exceptions on a ward (UX-05): what not to use, for every infection or the one in focus
 * (UX-08), and what is going on here now. Everything normal stays further down the page.
 */
export function WardExceptions({
  location,
  focus,
  filters,
  freshness,
}: {
  location: string;
  focus: InfectionFocus;
  filters: Filters;
  freshness: Freshness | null;
}) {
  const who = [
    filters.sex === "F" ? "women" : filters.sex === "M" ? "men" : null,
    filters.age_band ? `${filters.age_band} years` : null,
    filters.hospital_acquired === true ? "hospital-acquired" : filters.hospital_acquired === false ? "community onset" : null,
  ].filter(Boolean);

  return (
    <div className="exceptions">
      <section className="card pad exc-card exc-avoid">
        <h2>
          What to avoid
          {who.length > 0 && <span className="muted"> · {who.join(", ")}</span>}
        </h2>
        <AvoidAll location={location} focus={focus} filters={filters} />
      </section>
      <WardNow location={location} freshness={freshness} />
    </div>
  );
}

function useAvoid(location: string, infection: Infection, filters: Filters, enabled = true) {
  const { asOf, meta, alertsVersion } = useApp();
  return useFetch(
    (signal) => (enabled ? api.avoid({ location, infection, ...filters, as_of: asOf }, signal) : Promise.resolve(null)),
    [location, infection, enabled, filters.sex, filters.age_band, filters.hospital_acquired, asOf, alertsVersion, meta.data_version],
  );
}

/** Each infection as its own section, never pooled into one %; the ward's commonest first. */
function AvoidAll({ location, focus, filters }: { location: string; focus: InfectionFocus; filters: Filters }) {
  const on = (i: Infection) => focus === "all" || focus === i;
  const results = [
    useAvoid(location, "uti", filters, on("uti")),
    useAvoid(location, "bloodstream", filters, on("bloodstream")),
    useAvoid(location, "wound", filters, on("wound")),
  ];
  const error = results.find((r) => r.error)?.error;
  if (error) return <p className="error">Could not load the avoid list: {error}</p>;
  const loaded = results.map((r) => r.data).filter((d): d is Avoid => d !== null);
  if (loaded.length === 0) return <p className="muted small">Checking local resistance…</p>;
  // Own samples before borrowed ones, then by how many there are.
  loaded.sort(
    (a, b) => Number(a.organisms_from.fell_back) - Number(b.organisms_from.fell_back) || b.isolates - a.isolates,
  );
  const loading = results.some((r) => r.loading);

  return (
    <div className={loading ? "is-loading" : ""}>
      {loaded.map((d) => (
        <section key={d.infection} className="avoid-section">
          {focus === "all" && <h3>{d.infection_label}</h3>}
          <AvoidList data={d} full={focus !== "all"} />
        </section>
      ))}
    </div>
  );
}

/** One infection's avoid list, fetched (for the overview's ward level). */
export function AvoidFor({ location, infection }: { location: string; infection: Infection }) {
  const { data, error } = useAvoid(location, infection, {});
  if (error) return <p className="error">Could not load the avoid list: {error}</p>;
  if (!data) return <p className="muted small">Checking local resistance…</p>;
  return <AvoidList data={data} full={false} />;
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
