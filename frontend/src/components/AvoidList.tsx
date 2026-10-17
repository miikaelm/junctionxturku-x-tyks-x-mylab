import { api, type AvoidAgent, type AvoidOrganism, type Infection, type RecentRise } from "../api/client";
import { fmtDate, shortOrganism } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";
import type { Filters } from "./FilterBar";

const ARROW = { rising: "↑", easing: "↓", stable: "→" } as const;
const ARROW_TEXT = { rising: "rising", easing: "easing", stable: "stable" } as const;

export function monthYear(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { month: "short", year: "numeric" });
}

/**
 * What not to use (UX-05): antibiotics with a local reason to avoid them for this infection,
 * since when, and the direction. Agents without a warning are named on one line, so a doctor
 * can check the one they have in mind.
 */
export function AvoidList({
  location,
  infection,
  filters = {},
  compact = false,
}: {
  location: string;
  infection: Infection;
  filters?: Filters;
  compact?: boolean;
}) {
  const { asOf, meta } = useApp();
  const { data, error, loading } = useFetch(
    (signal) => api.avoid({ location, infection, ...filters, as_of: asOf }, signal),
    [location, infection, filters.sex, filters.age_band, filters.hospital_acquired, asOf, meta.data_version],
  );
  if (error) return <p className="error">Could not load the avoid list: {error}</p>;
  if (!data) return <p className="muted small">Checking local resistance…</p>;
  const label = data.infection_label.toLowerCase();
  const names = (xs: AvoidAgent[]) => xs.map((x) => x.name).join(", ");

  return (
    <div className={`avoid ${loading ? "is-loading" : ""}`}>
      {data.avoid.length === 0 && data.recent_rise.length === 0 ? (
        <p className="avoid-none">
          No antibiotic has a local resistance warning for a {label} here.
        </p>
      ) : (
        <ul className="avoid-list">
          {data.avoid.map((a) => (
            <AvoidItem key={a.code} agent={a} />
          ))}
          {data.recent_rise.map((a) => (
            <RiseItem key={a.code} agent={a} />
          ))}
        </ul>
      )}
      {!compact && (
        <dl className="avoid-rest">
          {data.no_warning.length > 0 && (
            <>
              <dt>No local warning</dt>
              <dd>{names(data.no_warning)}</dd>
            </>
          )}
          {data.not_suited.length > 0 && (
            <>
              <dt>Doesn't act on most of these organisms</dt>
              <dd>{names(data.not_suited)}</dd>
            </>
          )}
          {data.unknown.length > 0 && (
            <>
              <dt>Too little data to say</dt>
              <dd>{names(data.unknown)}</dd>
            </>
          )}
        </dl>
      )}
      <p className="muted small avoid-foot">
        Most {label}s here are caused by{" "}
        {data.main_organisms.map((o) => `${shortOrganism(o.organism)} (${Math.round(100 * o.share)} %)`).join(", ")}.
        Flagged when one of them is ≥ {data.threshold_pct} % resistant over the last 12 months (
        {fmtDate(data.window.start)} – {fmtDate(data.window.end)}, {data.isolates} first isolates
        {data.organisms_from.fell_back ? `, ${data.organisms_from.label}: too few here` : ""}). Decision support, not a
        prescription.
      </p>
    </div>
  );
}

function AvoidItem({ agent }: { agent: AvoidAgent }) {
  const above = agent.organisms.filter((o) => o.status === "above");
  return (
    <li className="avoid-item">
      <div className="avoid-head">
        <strong className="avoid-name">{agent.name}</strong>
        {agent.reserve && <span className="tag tag-muted">reserve</span>}
        <span className="avoid-since">
          since {agent.since_at_least ? `${monthYear(agent.since!)} or earlier` : monthYear(agent.since!)}
        </span>
        {agent.recent_rise && <span className="tag tag-rise">rising fast</span>}
      </div>
      <p className="avoid-why">
        {above.map((o, i) => (
          <span key={o.organism}>
            {i > 0 && " · "}
            <OrganismReason o={o} />
          </span>
        ))}
      </p>
    </li>
  );
}

/** A recent rise (active resistance-shift alert): the 12-month figure is still under the limit. */
function RiseItem({ agent }: { agent: AvoidAgent & { rise: RecentRise } }) {
  const r = agent.rise;
  return (
    <li className="avoid-item is-rise">
      <div className="avoid-head">
        <strong className="avoid-name">{agent.name}</strong>
        <span className="tag tag-rise">recent rise</span>
        <span className="avoid-since">since {fmtDate(r.since)}</span>
      </div>
      <p className="avoid-why">
        {shortOrganism(r.organism)} <strong className="mono">{Math.round(r.observed.pct!)} %</strong>{" "}
        <span className="muted mono small">
          ({r.observed.r}/{r.observed.n})
        </span>{" "}
        in the last 4 weeks, against {Math.round(r.expected.pct!)} % in the year before.{" "}
        <a href={href({ view: "alert", id: r.alert_id })}>Alert →</a>
      </p>
    </li>
  );
}

function OrganismReason({ o }: { o: AvoidOrganism }) {
  const d = o.direction;
  return (
    <span title={`95 % interval ${o.ci_low}–${o.ci_high} %${o.fell_back ? ` · ${o.level_label}: too few on the ward` : ""}`}>
      {shortOrganism(o.organism)} <strong className="mono">{Math.round(o.pct!)} %</strong>{" "}
      <span className="muted mono small">
        ({o.r}/{o.n}
        {o.fell_back ? `, ${o.level_label}` : ""})
      </span>
      {d && (
        <span className={`trend-arrow trend-${d}`} title={`Last 12 months vs the 12 before: ${ARROW_TEXT[d]}`}>
          {" "}
          {ARROW[d]} {ARROW_TEXT[d]}
        </span>
      )}
    </span>
  );
}
