import type { Avoid, AvoidAgent, AvoidOrganism, RecentRise } from "../api/client";
import { fmtDate, shortOrganism } from "../lib/format";
import { href } from "../lib/route";

const ARROW = { rising: "↑", easing: "↓", stable: "→" } as const;
const ARROW_TEXT = { rising: "rising", easing: "easing", stable: "stable" } as const;

export function monthYear(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { month: "short", year: "numeric" });
}

/**
 * What not to use for one infection (UX-05, UX-07), in two groups that say why: new first (a rise
 * in the last 4 weeks, with the alert that measured it and the outbreak it most likely comes from),
 * then long-standing (12-month figures, with since when, direction and the stewardship review).
 * Agents without a warning are named on one line, so a doctor can check the one they have in mind.
 */
export function AvoidList({ data, full = true }: { data: Avoid; full?: boolean }) {
  const label = data.infection_label.toLowerCase();
  const names = (xs: AvoidAgent[]) => xs.map((x) => x.name).join(", ");
  const none = data.avoid.length === 0 && data.recent_rise.length === 0;

  return (
    <div className="avoid">
      {none && <p className="avoid-none">No antibiotic has a local resistance warning for a {label} here.</p>}
      {data.recent_rise.length > 0 && (
        <div className="avoid-group">
          <p className="avoid-group-label">
            <span className="tag tag-rise">New</span> risen in the last 4 weeks; the 12-month figure is still under{" "}
            {data.threshold_pct} %
          </p>
          <ul className="avoid-list">
            {data.recent_rise.map((a) => (
              <RiseItem key={a.code} agent={a} />
            ))}
          </ul>
        </div>
      )}
      {data.avoid.length > 0 && (
        <div className="avoid-group">
          <p className="avoid-group-label">
            <span className="tag tag-long">Long-standing</span> ≥ {data.threshold_pct} % resistant over the last 12 months
          </p>
          <ul className="avoid-list">
            {data.avoid.map((a) => (
              <AvoidItem key={a.code} agent={a} />
            ))}
          </ul>
        </div>
      )}
      <dl className="avoid-rest">
        {data.no_warning.length > 0 && (
          <>
            <dt>No local warning</dt>
            <dd>{names(data.no_warning)}</dd>
          </>
        )}
        {full && data.not_suited.length > 0 && (
          <>
            <dt>Doesn't act on most of these organisms</dt>
            <dd>{names(data.not_suited)}</dd>
          </>
        )}
        {full && data.unknown.length > 0 && (
          <>
            <dt>Too little data to say</dt>
            <dd>{names(data.unknown)}</dd>
          </>
        )}
      </dl>
      <p className="muted small avoid-foot">
        Most {label}s here are caused by{" "}
        {data.main_organisms.map((o) => `${shortOrganism(o.organism)} (${Math.round(100 * o.share)} %)`).join(", ")}
        {data.organisms_from.fell_back ? ` (from ${data.organisms_from.label}: too few samples here)` : ""}. Based on{" "}
        {data.isolates} first isolates, {fmtDate(data.window.start)} – {fmtDate(data.window.end)}. Decision support, not a
        prescription.
      </p>
    </div>
  );
}

function AvoidItem({ agent }: { agent: AvoidAgent }) {
  const above = agent.organisms.filter((o) => o.status === "above");
  const finding = above.find((o) => o.finding)?.finding;
  return (
    <li className="avoid-item">
      <div className="avoid-head">
        <strong className="avoid-name">{agent.name}</strong>
        {agent.reserve && <span className="tag tag-muted">reserve</span>}
        <span className="avoid-since">
          high since {agent.since_at_least ? `${monthYear(agent.since!)} or earlier` : monthYear(agent.since!)}
        </span>
      </div>
      <p className="avoid-why">
        {above.map((o, i) => (
          <span key={o.organism}>
            {i > 0 && " · "}
            <OrganismReason o={o} />
          </span>
        ))}
      </p>
      {agent.recent_rise && (
        <p className="avoid-also">
          <span className="tag tag-rise">Also new</span> {Math.round(agent.recent_rise.observed.pct!)} % (
          {agent.recent_rise.observed.r}/{agent.recent_rise.observed.n}) in the last 4 weeks.{" "}
          <RiseLinks rise={agent.recent_rise} />
        </p>
      )}
      {finding && (
        <p className="avoid-review small">
          <a href={href({ view: "finding", id: finding.id })}>
            Stewardship: <span className={`review-text review-${finding.status}`}>{finding.label.toLowerCase()}</span>
            {finding.as_of && finding.status !== "new" ? ` (${fmtDate(finding.as_of)})` : ""} →
          </a>
        </p>
      )}
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
        <span className="avoid-since">since {fmtDate(r.since)}</span>
      </div>
      <p className="avoid-why">
        {shortOrganism(r.organism)} <strong className="mono">{Math.round(r.observed.pct!)} %</strong>{" "}
        <span className="muted mono small">
          ({r.observed.r}/{r.observed.n})
        </span>{" "}
        in the last 4 weeks, against {Math.round(r.expected.pct!)} % in the year before.
      </p>
      <p className="avoid-links small">
        <RiseLinks rise={r} />
      </p>
    </li>
  );
}

/** The two things a rise relates to, each named for what it is (UX-07). */
function RiseLinks({ rise }: { rise: RecentRise }) {
  return (
    <span className="rise-links">
      <span>
        Measured by: <a href={href({ view: "alert", id: rise.alert_id })}>resistance-shift alert</a>
      </span>
      {rise.cause && (
        <span>
          Likely cause:{" "}
          <a href={href({ view: "alert", id: rise.cause.alert_id })}>
            {rise.cause.type_label.toLowerCase()} on {rise.cause.wards.join(", ")}
          </a>{" "}
          <span className="muted">
            ({rise.cause.matching} of the {rise.cause.of} resistant isolates are its cases)
          </span>
        </span>
      )}
    </span>
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
