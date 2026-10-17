import type { AlertTimeline } from "../api/client";
import { fmtDate } from "../lib/format";

/**
 * Plain SVG bar chart for alert timelines (counts per day/week, or resistance % per 4 weeks
 * with its 95 % interval). A dashed line marks the expected level.
 */
export function BarChart({ timeline }: { timeline: AlertTimeline }) {
  const W = 720;
  const H = 180;
  const pad = { l: 36, r: 8, t: 10, b: 22 };
  const isRate = timeline.kind === "rate";
  const values = timeline.points.map((p) => (isRate ? (p.pct ?? 0) : (p.value ?? 0)));
  const highs = timeline.points.map((p) => (isRate ? (p.n ? (p.ci_high ?? 0) : 0) : (p.value ?? 0)));
  const max = Math.max(1, timeline.expected ?? 0, ...highs) * 1.1;
  const n = timeline.points.length;
  const bw = (W - pad.l - pad.r) / n;
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const ticks = [0, max / 2, max].map((v) => (isRate ? Math.round(v) : Math.round(v * 10) / 10));

  return (
    <figure className="chart">
      <figcaption>{timeline.label}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={timeline.label}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className="chart-grid" />
            <text x={pad.l - 6} y={y(t) + 4} className="chart-tick" textAnchor="end">
              {t}
              {isRate ? "%" : ""}
            </text>
          </g>
        ))}
        {timeline.points.map((p, i) => {
          const v = values[i];
          const x = pad.l + i * bw;
          const thin = isRate && (p.n ?? 0) < 30;
          const tip = isRate
            ? `${fmtDate(p.start)} – ${fmtDate(p.end)}: ${p.n ? `${p.r}/${p.n} resistant (${p.pct} %, 95 % CI ${p.ci_low}–${p.ci_high})` : "no isolates"}`
            : `${fmtDate(p.start)}${p.start !== p.end ? ` – ${fmtDate(p.end)}` : ""}: ${v}`;
          return (
            <g key={p.start}>
              <title>{tip}</title>
              <rect
                x={x + 1}
                y={y(v)}
                width={Math.max(1, bw - 2)}
                height={y(0) - y(v)}
                className={`chart-bar ${thin ? "is-thin" : ""}`}
              />
              {isRate && p.n ? (
                <line x1={x + bw / 2} x2={x + bw / 2} y1={y(p.ci_low ?? 0)} y2={y(p.ci_high ?? 0)} className="chart-ci" />
              ) : null}
            </g>
          );
        })}
        {timeline.expected !== null && (
          <line x1={pad.l} x2={W - pad.r} y1={y(timeline.expected)} y2={y(timeline.expected)} className="chart-expected" />
        )}
        <text x={pad.l} y={H - 6} className="chart-tick">
          {fmtDate(timeline.points[0].start)}
        </text>
        <text x={W - pad.r} y={H - 6} className="chart-tick" textAnchor="end">
          {fmtDate(timeline.points[n - 1].end)}
        </text>
      </svg>
      <p className="chart-note muted small">
        Per {timeline.unit}.
        {timeline.expected !== null && <> Dashed line: expected ({isRate ? `${timeline.expected} %` : timeline.expected}).</>}
        {isRate && <> Lighter bars: fewer than 30 isolates. Whiskers: 95 % interval.</>}
      </p>
    </figure>
  );
}
