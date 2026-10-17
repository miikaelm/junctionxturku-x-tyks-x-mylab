import type { CSSProperties } from "react";
import { api, type Overview as OverviewData, type OverviewCell } from "../api/client";
import { fmtDate, pct, shortOrganism, tier } from "../lib/format";
import { useFetch, useLocalStorage } from "../lib/hooks";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";

const SPANS = [
  { key: "26w", label: "26 weeks, weekly", bins: 26, days: 7 },
  { key: "52w", label: "52 weeks, weekly", bins: 52, days: 7 },
  { key: "13x4w", label: "1 year, 4-week blocks", bins: 13, days: 28 },
  { key: "12q", label: "3 years, quarters (13 weeks)", bins: 12, days: 91 },
];

/** V5 Ward × time overview: where and when things changed, with the alerts raised there. */
export function Overview() {
  const { meta, asOf } = useApp();
  const [metric, setMetric] = useLocalStorage("aei.overview.metric", "phenotype:ESBL");
  const isRate = metric.startsWith("rate:");
  const rate = isRate ? meta.key_rates[Number(metric.split(":")[1])] : undefined;
  const [spanKey, setSpanKey] = useLocalStorage<string | null>("aei.overview.span", null);
  const span = SPANS.find((s) => s.key === spanKey) ?? (isRate ? SPANS[2] : SPANS[0]);

  const { data, error, loading } = useFetch(
    (signal) =>
      api.overview(
        rate
          ? {
              metric: "rate",
              specimen: rate.specimen,
              organism: rate.organism,
              antibiotic: rate.antibiotic,
              bins: span.bins,
              bin_days: span.days,
              as_of: asOf,
            }
          : { metric: "phenotype", phenotype: metric.split(":")[1], bins: span.bins, bin_days: span.days, as_of: asOf },
        signal,
      ),
    [metric, span.key, asOf, meta.data_version],
  );

  return (
    <>
      <section className="ward-head">
        <div>
          <p className="eyebrow">Infection control</p>
          <h1>Ward × time overview</h1>
          <p className="ward-sub">Every ward side by side, latest on the right · as of {fmtDate(asOf)}</p>
        </div>
      </section>

      <div className="filters">
        <div className="filters-patient">
          <label className="field">
            <span className="field-label">Show</span>
            <select value={metric} onChange={(e) => setMetric(e.target.value)}>
              <optgroup label="New resistant cases">
                {meta.phenotypes.map((p) => (
                  <option key={p} value={`phenotype:${p}`}>
                    {p} cases
                  </option>
                ))}
              </optgroup>
              <optgroup label="Key resistance rates (first isolates)">
                {meta.key_rates.map((k, i) => (
                  <option key={i} value={`rate:${i}`}>
                    {shortOrganism(k.organism)} {k.antibiotic_name} ({k.specimen})
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Columns</span>
            <select value={span.key} onChange={(e) => setSpanKey(e.target.value)}>
              {SPANS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error && <p className="error">Could not load the overview: {error}</p>}
      {data && (
        <div className={`card pad ${loading ? "is-loading" : ""}`}>
          <Grid data={data} />
          <p className="muted small table-foot">
            {data.kind === "count"
              ? "New cases per ward and period (a patient's repeat positives within 90 days count once). Darker = more cases."
              : `Resistance among first isolates per ward and period. A percentage and colour only with at least ${meta.thresholds.min_isolates} isolates; otherwise resistant/tested in grey.`}{" "}
            A ring marks a period in which an alert was raised for this ward; click it to open the alert.
          </p>
        </div>
      )}
    </>
  );
}

function Grid({ data }: { data: OverviewData }) {
  const { meta } = useApp();
  const max = Math.max(
    1,
    ...data.rows.filter((r) => r.ward !== "ALL").flatMap((r) => r.cells.map((c) => c.value ?? 0)),
  );
  const every = Math.ceil(data.bins.length / 8);
  return (
    <div className="table-scroll">
      <table className="grid">
        <thead>
          <tr>
            <th />
            {data.bins.map((b, i) => (
              <th key={b.start} className="grid-col" title={`${fmtDate(b.start)} – ${fmtDate(b.end)}`}>
                {i % every === 0 ? shortDate(b.start) : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row) => (
            <tr key={row.ward} className={row.ward === "ALL" ? "grid-total" : ""}>
              <th scope="row" className="grid-ward" title={row.label}>
                {row.ward === "ALL" ? "All" : row.ward}
              </th>
              {row.cells.map((c, i) => (
                <GridCell key={i} cell={c} kind={data.kind} max={max} bin={data.bins[i]} thresholds={meta.thresholds} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GridCell({
  cell,
  kind,
  max,
  bin,
  thresholds,
}: {
  cell: OverviewCell;
  kind: "count" | "rate";
  max: number;
  bin: { start: string; end: string };
  thresholds: Parameters<typeof tier>[1];
}) {
  const alerts = cell.alerts ?? [];
  const period = `${fmtDate(bin.start)} – ${fmtDate(bin.end)}`;
  let text = "";
  let style: CSSProperties = {};
  let cls = "";
  let tip: string;
  if (kind === "count") {
    const v = cell.value ?? 0;
    text = v ? String(v) : "";
    style = v ? { background: `color-mix(in srgb, var(--bad) ${Math.round(15 + 70 * Math.min(1, v / max))}%, var(--surface))` } : {};
    cls = v / max > 0.5 ? "grid-dark" : "";
    tip = `${period}: ${v} new case${v === 1 ? "" : "s"}`;
  } else {
    const n = cell.n ?? 0;
    const t = tier(cell as Parameters<typeof tier>[0], thresholds);
    cls = `tier-${t}`;
    text = !n ? "" : cell.sufficient ? pct(cell.pct ?? null) : `${cell.r}/${n}`;
    tip = n ? `${period}: ${cell.r}/${n} resistant${cell.sufficient ? ` (${cell.pct} %)` : " (too few for a %)"}` : `${period}: no isolates`;
  }
  if (alerts.length) tip += `\n${alerts.map((a) => `${a.type_label}: ${a.title} (${fmtDate(a.first_seen)})`).join("\n")}`;
  const body = <span className="grid-val">{text}</span>;
  return (
    <td className={`grid-cell ${cls} ${alerts.length ? "has-alert" : ""}`} style={style} title={tip}>
      {alerts.length ? (
        <a href={href({ view: "alert", id: alerts[0].id })} aria-label={tip}>
          {body}
        </a>
      ) : (
        body
      )}
    </td>
  );
}

function shortDate(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit" });
}
