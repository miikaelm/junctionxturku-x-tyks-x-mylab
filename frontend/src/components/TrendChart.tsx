import type { TrendSeries } from "../api/client";
import { fmtDate } from "../lib/format";

/**
 * Quarterly resistance with 95 % intervals, the fitted linear trend and the empirical-use
 * threshold line (V6). Plain SVG.
 */
export function TrendChart({ series, minN }: { series: TrendSeries; minN: number }) {
  const W = 760;
  const H = 240;
  const pad = { l: 40, r: 12, t: 12, b: 28 };
  const pts = series.points;
  const highs = pts.map((p) => (p.n ? p.ci_high : 0));
  const max = Math.min(100, Math.max(series.threshold_pct * 1.3, ...highs, ...pts.map((p) => p.fitted ?? 0)) * 1.1);
  const step = (W - pad.l - pad.r) / pts.length;
  const x = (i: number) => pad.l + step * (i + 0.5);
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const ticks = [0, max / 2, max].map((v) => Math.round(v));
  const fitted = pts.map((p, i) => (p.fitted === null ? null : `${x(i)},${y(Math.max(0, p.fitted))}`)).filter(Boolean);
  const label = `${series.organism} × ${series.antibiotic}, ${series.scope.label} (${series.scope.specimen})`;

  return (
    <figure className="chart">
      <figcaption>{label}: resistance per quarter, first isolates</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className="chart-grid" />
            <text x={pad.l - 6} y={y(t) + 4} className="chart-tick" textAnchor="end">
              {t}%
            </text>
          </g>
        ))}
        <line
          x1={pad.l}
          x2={W - pad.r}
          y1={y(series.threshold_pct)}
          y2={y(series.threshold_pct)}
          className="chart-threshold"
        />
        <text x={pad.l + 4} y={y(series.threshold_pct) - 4} className="chart-tick chart-threshold-label">
          {series.threshold_pct} % empirical-use limit
        </text>
        {fitted.length > 1 && <polyline points={fitted.join(" ")} className="chart-fit" />}
        {pts.map((p, i) => (
          <g key={p.label} className={p.n < minN ? "is-thin" : ""}>
            <title>
              {p.label} ({fmtDate(p.start)} – {fmtDate(p.end)}):{" "}
              {p.n ? `${p.r}/${p.n} resistant, ${p.pct} % (95 % CI ${p.ci_low}–${p.ci_high})` : "no isolates"}
            </title>
            {p.n > 0 && (
              <>
                <line x1={x(i)} x2={x(i)} y1={y(p.ci_low)} y2={y(p.ci_high)} className="chart-ci" />
                <circle cx={x(i)} cy={y(p.pct ?? 0)} r={4} className="chart-dot" />
              </>
            )}
            <text x={x(i)} y={H - 10} className="chart-tick" textAnchor="middle">
              {i % 2 === 0 || pts.length <= 8 ? p.label.replace(" ", " ") : ""}
            </text>
          </g>
        ))}
      </svg>
      <p className="chart-note muted small">
        Dots: resistance per calendar quarter (the last one runs to the as-of date); whiskers: 95 % interval; faded:
        fewer than {minN} isolates. Solid line: fitted linear trend. Dashed red line: {series.threshold_pct} % limit.
      </p>
    </figure>
  );
}
