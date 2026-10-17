import { useState } from "react";
import { api, type Infection, type Specimen, type TherapyAgent } from "../api/client";
import { fmtDate, shortOrganism } from "../lib/format";
import { useFetch, useLocalStorage } from "../lib/hooks";
import { useApp } from "../state/AppContext";
import type { Filters } from "./FilterBar";

const INFECTION_OF: Record<Specimen, Infection> = { urine: "uti", blood: "bloodstream", wound: "wound" };

/**
 * Therapy helper (V2, VIEW-04): best-covering antibiotics for this infection on this ward, for a
 * patient like the one filtered for. Uses the page's ward, specimen and patient filters.
 */
export function TherapyHelper({ location, specimen, filters }: { location: string; specimen: Specimen; filters: Filters }) {
  const { meta, asOf } = useApp();
  const [open, setOpen] = useLocalStorage("aei.therapy.ranking.open", false);
  const [detail, setDetail] = useState<string | null>(null);
  const infection = INFECTION_OF[specimen];
  const { data, error, loading } = useFetch(
    (signal) =>
      open
        ? api.therapy({ location, infection, ...filters, as_of: asOf }, signal)
        : Promise.resolve(null),
    [open, location, infection, filters.sex, filters.age_band, filters.hospital_acquired, asOf, meta.data_version],
  );
  const label = meta.infections.find((i) => i.key === infection)?.label ?? infection;
  const who = [
    filters.sex === "F" ? "women" : filters.sex === "M" ? "men" : null,
    filters.age_band ? `${filters.age_band} years` : null,
    filters.hospital_acquired === true ? "hospital-acquired" : filters.hospital_acquired === false ? "community onset" : null,
  ].filter(Boolean);
  const shown = data?.ranked.find((x) => x.code === detail) ?? data?.unranked.find((x) => x.code === detail);

  return (
    <section className={`card pad therapy ${loading ? "is-loading" : ""}`}>
      <div className="therapy-head">
        <h2>
          Coverage ranking for a {label.toLowerCase()}
          {who.length > 0 && <span className="muted"> · {who.join(", ")}</span>}
        </h2>
        <button type="button" className="link-btn" onClick={() => setOpen(!open)}>
          {open ? "Hide" : "Show"}
        </button>
      </div>
      {open && error && <p className="error">Could not load the therapy helper: {error}</p>}
      {open && data && (
        <>
          <p className="muted small">
            Estimated share of {label.toLowerCase()}s on <strong>{data.used.label}</strong> each antibiotic would cover,
            weighting each organism by how often it causes them here. {data.isolates} first isolates,{" "}
            {fmtDate(data.window.start)} – {fmtDate(data.window.end)}.
            {data.used.fell_back && (
              <strong> Too few on {data.scope.label} for this patient group: showing {data.used.label}.</strong>
            )}
            {!data.sufficient && <strong> Fewer than {meta.thresholds.min_isolates} isolates even there: read with care.</strong>}
          </p>
          <ol className="therapy-strip">
            {data.ranked.slice(0, 6).map((x) => (
              <li key={x.code}>
                <button
                  type="button"
                  className={`therapy-chip tier-${x.tier} ${detail === x.code ? "on" : ""}`}
                  onClick={() => setDetail(detail === x.code ? null : x.code)}
                  title={`95 % interval ${x.ci_low}–${x.ci_high} %`}
                >
                  <span className="therapy-name">
                    {x.name}
                    {x.reserve && <span className="tag tag-muted">reserve</span>}
                  </span>
                  <span className="therapy-pct mono">{Math.round(x.coverage_pct)} %</span>
                  <span className="therapy-ci mono">
                    {Math.round(x.ci_low)}–{Math.round(x.ci_high)}
                  </span>
                </button>
              </li>
            ))}
          </ol>
          {shown && <AgentDetail agent={shown} />}
          <details className="small">
            <summary>
              All {data.ranked.length + data.unranked.length} antibiotics
              {data.unranked.length > 0 && `, ${data.unranked.length} not ranked (not tested on most organisms here)`}
            </summary>
            <table className="table compact">
              <thead>
                <tr>
                  <th>Antibiotic</th>
                  <th>Coverage</th>
                  <th>95 % interval</th>
                  <th>Not tested on</th>
                </tr>
              </thead>
              <tbody>
                {[...data.ranked, ...data.unranked].map((x) => (
                  <tr key={x.code} className="row-click" onClick={() => setDetail(x.code)}>
                    <td>
                      <span className="mono">{x.code}</span> {x.name}
                      {x.reserve && <span className="tag tag-muted">reserve</span>}
                    </td>
                    <td className={`mono tier-text-${x.tier}`}>{Math.round(x.coverage_pct)} %</td>
                    <td className="mono">
                      {x.ci_low}–{x.ci_high} %
                    </td>
                    <td className="small">
                      {x.not_tested.length
                        ? `${x.not_tested.map(shortOrganism).join(", ")} (${Math.round(100 * x.not_tested_share)} %)`
                        : "–"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          <p className="muted small">
            Decision support, not a prescription: follow the local guideline: reserve agents rank high by coverage
            but are kept for resistant infections. Organisms an antibiotic was never tested on count as not covered.
          </p>
        </>
      )}
    </section>
  );
}

function AgentDetail({ agent }: { agent: TherapyAgent }) {
  return (
    <div className="therapy-detail">
      <p>
        <strong>{agent.name}</strong> covers an estimated <strong>{agent.coverage_pct} %</strong> (95 % interval{" "}
        {agent.ci_low}–{agent.ci_high} %):
      </p>
      <table className="table compact">
        <thead>
          <tr>
            <th>Likely organism</th>
            <th>Share of infections</th>
            <th>Susceptible</th>
          </tr>
        </thead>
        <tbody>
          {agent.organisms.map((o) => (
            <tr key={o.organism}>
              <td>{o.organism}</td>
              <td className="mono">{Math.round(100 * o.share)} %</td>
              <td className="small">
                {o.status === "intrinsic"
                  ? "intrinsically resistant"
                  : o.status === "not_tested"
                    ? "not tested (counted as not covered)"
                    : `${o.susceptible_pct} % (${(o.n ?? 0) - (o.r ?? 0)}/${o.n})${o.status === "inferred" ? `, inferred from ${o.inferred_from} screen` : ""}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
