import { useState } from "react";
import {
  api,
  type Estimate,
  type Specimen,
  type TrendFinding,
  type TrendFindings,
  type TrendSeries,
} from "../api/client";
import { fmtP } from "../components/AlertBits";
import { SubgroupPanel } from "../components/SubgroupPanel";
import { TrendChart } from "../components/TrendChart";
import { fmtDate, pct, shortOrganism } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { useApp } from "../state/AppContext";
import { FindingsToReview } from "./Stewardship";

interface Selection {
  location: string;
  specimen: Specimen;
  organism: string;
  antibiotic: string;
}

/**
 * Stewardship (V6): findings to review (ANOM-10) first, then the trend explorer (ANOM-03): long-term
 * trends, the empirical-use threshold, year vs year.
 */
export function Trends() {
  const { meta, asOf } = useApp();
  const findings = useFetch((signal) => api.trendFindings(asOf, signal), [asOf, meta.data_version]);
  const [chosen, setChosen] = useState<Selection | null>(null);
  const top = findings.data?.trends[0];
  const sel: Selection = chosen ??
    (top && { location: top.location, specimen: top.specimen, organism: top.organism, antibiotic: top.antibiotic_code }) ?? {
      location: "all",
      specimen: "urine",
      organism: "Escherichia coli",
      antibiotic: "CIP",
    };
  const pick = (f: TrendFinding) =>
    setChosen({ location: f.location, specimen: f.specimen, organism: f.organism, antibiotic: f.antibiotic_code });

  return (
    <>
      <section className="ward-head">
        <div>
          <p className="eyebrow">Lab &amp; stewardship</p>
          <h1>Stewardship</h1>
          <p className="ward-sub">
            Long-standing resistance to review, and slow changes over the years · as of {fmtDate(asOf)}
          </p>
        </div>
      </section>

      <h2 className="section-title">Findings to review</h2>
      <FindingsToReview />

      <h2 className="section-title">Trend tests, all series</h2>
      {findings.error && <p className="error">Could not load trend findings: {findings.error}</p>}
      {findings.data && <Findings data={findings.data} onPick={pick} />}

      <h2 className="section-title">Explore a series</h2>
      <SeriesPicker sel={sel} onChange={setChosen} />
      <Series sel={sel} />
      <SubgroupPanel location={sel.location} specimen={sel.specimen} />
    </>
  );
}

function Findings({ data, onPick }: { data: TrendFindings; onPick: (f: TrendFinding) => void }) {
  const up = data.crossings.filter((c) => c.direction === "up");
  const down = data.crossings.filter((c) => c.direction === "down");
  return (
    <div className="trend-findings">
      <section className="card pad">
        <h2>Significant long-term trends</h2>
        {data.trends.length === 0 ? (
          <p className="muted">No significant trend among {data.tested} series.</p>
        ) : (
          <FindingTable rows={data.trends} onPick={onPick} trend />
        )}
        <p className="muted small method">
          Cochran–Armitage trend test over calendar quarters (first isolates per quarter) for every location × specimen ×
          organism × antibiotic with at least 6 quarters and 100 isolates; {data.tested} series tested, false-discovery
          rate 5 %, changes under 5 percentage points over the period ignored.
        </p>
      </section>
      <section className="card pad">
        <h2>Crossed the {data.threshold_pct} % empirical-use limit</h2>
        {up.length === 0 ? (
          <p className="muted">Nothing crossed the limit upwards in the last 12 months.</p>
        ) : (
          <FindingTable rows={up} onPick={onPick} />
        )}
        {down.length > 0 && (
          <details className="small">
            <summary>{down.length} fell below the limit</summary>
            <FindingTable rows={down} onPick={onPick} />
          </details>
        )}
        <p className="muted small method">
          Last 12 months vs the 12 months before, both with at least 30 first isolates. Where the 95 % interval still
          spans the line, the crossing may be chance: watch it rather than act on it.
        </p>
      </section>
    </div>
  );
}

function FindingTable({
  rows,
  onPick,
  trend = false,
}: {
  rows: (TrendFinding & { clearly?: boolean })[];
  onPick: (f: TrendFinding) => void;
  trend?: boolean;
}) {
  return (
    <div className="table-scroll">
      <table className="table compact">
        <thead>
          <tr>
            <th>Where</th>
            <th>Organism × antibiotic</th>
            <th>12 months before</th>
            <th>Last 12 months</th>
            <th>{trend ? "Trend" : "95 % CI past the line?"}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((f) => (
            <tr key={`${f.location}-${f.specimen}-${f.organism}-${f.antibiotic_code}`} className="row-click" onClick={() => onPick(f)}>
              <td>
                {f.location_label} <span className="muted">· {f.specimen}</span>
              </td>
              <td>
                {shortOrganism(f.organism)} × <span className="mono">{f.antibiotic_code}</span>
              </td>
              <td className="mono">{rate(f.prev_12m)}</td>
              <td className="mono">{rate(f.last_12m)}</td>
              <td className="mono">
                {trend && f.trend
                  ? `${f.trend.pp_per_year > 0 ? "+" : ""}${f.trend.pp_per_year} pp/yr · q ${fmtP(f.trend.q_value ?? undefined)}`
                  : f.clearly
                    ? "yes"
                    : "no"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function rate(e: Estimate) {
  return e.n ? `${pct(e.pct)} (${e.r}/${e.n})` : "–";
}

function SeriesPicker({ sel, onChange }: { sel: Selection; onChange: (s: Selection) => void }) {
  const { meta } = useApp();
  const intrinsic = (o: string, a: string) => meta.intrinsic[o]?.includes(a) ?? false;
  const tested = new Set(meta.tested_pairs.map(([o, a]) => `${o}|${a}`));
  const abxFor = (specimen: Specimen, organism: string) =>
    meta.antibiotics.filter(
      (a) =>
        (a.reported_for === "all" || a.reported_for === specimen) &&
        tested.has(`${organism}|${a.code}`) &&
        !intrinsic(organism, a.code),
    );
  const organisms = meta.organisms.filter((o) => abxFor(sel.specimen, o).length > 0);
  const abx = abxFor(sel.specimen, sel.organism);
  const set = (patch: Partial<Selection>) => {
    const next = { ...sel, ...patch };
    const options = abxFor(next.specimen, next.organism);
    if (!options.some((a) => a.code === next.antibiotic)) next.antibiotic = options[0]?.code ?? "";
    onChange(next);
  };

  return (
    <div className="filters">
      <div className="filters-patient">
        <label className="field">
          <span className="field-label">Location</span>
          <select value={sel.location} onChange={(e) => set({ location: e.target.value })}>
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
          <span className="field-label">Specimen</span>
          <select value={sel.specimen} onChange={(e) => set({ specimen: e.target.value as Specimen })}>
            {meta.specimens.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Organism</span>
          <select value={sel.organism} onChange={(e) => set({ organism: e.target.value })}>
            {organisms.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Antibiotic</span>
          <select value={sel.antibiotic} onChange={(e) => set({ antibiotic: e.target.value })}>
            {abx.map((a) => (
              <option key={a.code} value={a.code}>
                {a.code} · {a.name}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}

export function Series({ sel }: { sel: Selection }) {
  const { meta, asOf } = useApp();
  const { data, error, loading } = useFetch(
    (signal) => (sel.antibiotic ? api.trendSeries({ ...sel, as_of: asOf }, signal) : Promise.resolve(null)),
    [sel.location, sel.specimen, sel.organism, sel.antibiotic, asOf, meta.data_version],
  );
  if (error) return <p className="error">Could not load the series: {error}</p>;
  if (!data) return null;
  return (
    <div className={loading ? "is-loading" : ""}>
      <section className="card pad">
        <p className="trend-summary">{summary(data)}</p>
        <TrendChart series={data} minN={meta.thresholds.min_isolates} />
      </section>
      <section className="card pad">
        <h2>Year by year</h2>
        <div className="table-scroll">
          <table className="table compact">
            <thead>
              <tr>
                <th>Period</th>
                <th>Resistant</th>
                <th>%</th>
                <th>95 % CI</th>
              </tr>
            </thead>
            <tbody>
              {data.years.map((y) => (
                <tr key={y.year}>
                  <td>
                    {y.year}
                    {y.partial && (
                      <span className="muted small">
                        {" "}
                        ({fmtDate(y.start)} – {fmtDate(y.end)})
                      </span>
                    )}
                  </td>
                  <td className="mono">
                    {y.r}/{y.n}
                  </td>
                  <td className="mono">{y.sufficient ? pct(y.pct) : "too few"}</td>
                  <td className="mono">{y.n ? `${Math.round(y.ci_low)}–${Math.round(y.ci_high)} %` : "–"}</td>
                </tr>
              ))}
              {(["previous", "last"] as const).map((k) => {
                const p = data.year_vs_year[k];
                return (
                  <tr key={k} className="row-strong">
                    <td>
                      {k === "last" ? "Last 12 months" : "12 months before"}{" "}
                      <span className="muted small">
                        ({fmtDate(p.start)} – {fmtDate(p.end)})
                      </span>
                    </td>
                    <td className="mono">
                      {p.r}/{p.n}
                    </td>
                    <td className="mono">{p.sufficient ? pct(p.pct) : "too few"}</td>
                    <td className="mono">{p.n ? `${Math.round(p.ci_low)}–${Math.round(p.ci_high)} %` : "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="muted small table-foot">
          Last 12 months vs the 12 months before: p {fmtP(data.year_vs_year.p_value ?? undefined)} (
          {data.year_vs_year.method}).
        </p>
      </section>
    </div>
  );
}

function summary(s: TrendSeries): string {
  const t = s.trend;
  if (!t || !t.eligible) {
    return `Too little data for a trend test here (needs 6 quarters and 100 first isolates; ${t?.n ?? 0} isolates).`;
  }
  const dir = t.direction === "up" ? "increasing" : "decreasing";
  const rate = `${Math.abs(t.pp_per_year)} percentage points per year`;
  let out = t.significant
    ? `Significant ${dir} trend: about ${rate} (${t.change_pp > 0 ? "+" : ""}${t.change_pp} pp over the period, q ${fmtP(t.q_value ?? undefined)}).`
    : t.q_value === null
      ? `No trend flagged: ${dir} by ${rate}, under 5 percentage points over the period.`
      : `${dir[0].toUpperCase()}${dir.slice(1)} by ${rate} (p ${fmtP(t.p_value)}), but not significant once corrected for all the series tested (q ${fmtP(t.q_value)}).`;
  if (s.trend_crosses_threshold) out += ` The trend line crosses ${s.threshold_pct} % in ${s.trend_crosses_threshold}.`;
  return out;
}
