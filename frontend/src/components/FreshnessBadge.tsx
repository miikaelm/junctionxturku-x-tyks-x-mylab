import type { Freshness, WardFreshness } from "../api/client";
import { daysAgo, fmtDate } from "../lib/format";
import { useApp } from "../state/AppContext";

const RANK: Record<WardFreshness["status"], number> = { ok: 0, delayed: 1, stale: 2, no_data: 3 };

const TEXT: Record<WardFreshness["status"], string> = {
  ok: "Data current",
  delayed: "Data delayed",
  stale: "Data missing",
  no_data: "No data",
};

/**
 * Data-freshness badge (VIEW-12): "no data" must never be mistaken for "no resistance".
 * For a combined location it reports the worst ward in it; the dropdown lists every ward.
 */
export function FreshnessBadge({ freshness, location }: { freshness: Freshness | null; location: string }) {
  const { meta } = useApp();
  if (!freshness) return <div className="fresh fresh-loading">Checking data feed…</div>;

  const inScope = freshness.wards.filter((w) => {
    if (location === "all") return true;
    const ward = meta.wards.find((m) => m.ward_code === w.ward_code);
    return w.ward_code === location || ward?.institution === location;
  });
  const worst = inScope.reduce((a, b) => (RANK[b.status] > RANK[a.status] ? b : a), inScope[0]);
  const single = inScope.length === 1;
  const detail = single
    ? `Last sample ${daysAgo(worst.days_since_last)}`
    : worst.status === "ok"
      ? `All ${inScope.length} wards reporting`
      : `${worst.ward_code}: last sample ${daysAgo(worst.days_since_last)}`;
  const othersWithIssues = freshness.wards.filter((w) => w.status !== "ok" && !inScope.includes(w)).length;

  return (
    <details className={`fresh fresh-${worst.status}`}>
      <summary>
        <span className="fresh-dot" aria-hidden />
        <span className="fresh-text">
          <strong>{TEXT[worst.status]}</strong>
          <span>{detail}</span>
          {othersWithIssues > 0 && (
            <span className="fresh-others">
              {othersWithIssues} other ward{othersWithIssues > 1 ? "s" : ""} with feed issues
            </span>
          )}
        </span>
      </summary>
      <div className="fresh-pop">
        <p className="fresh-pop-title">Feed status as of {fmtDate(freshness.as_of)}</p>
        <table>
          <tbody>
            {freshness.wards.map((w) => (
              <tr key={w.ward_code} className={`fresh-row fresh-${w.status}`}>
                <td>
                  <span className="fresh-dot" aria-hidden />
                </td>
                <td className="mono">{w.ward_code}</td>
                <td>{daysAgo(w.days_since_last)}</td>
                <td className="muted">{w.samples_per_day} / day</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="fresh-pop-note">
          A ward is flagged when its silence is very unlikely given its usual sample rate. Missing
          data means results may be incomplete, not that resistance is absent.
        </p>
      </div>
    </details>
  );
}
