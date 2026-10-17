import { api, type FeedWard } from "../api/client";
import { AlertList } from "../components/AlertBits";
import { addDays, daysAgo, fmtDate } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { useApp } from "../state/AppContext";

const STATUS_TEXT: Record<FeedWard["status"], string> = {
  ok: "Current",
  delayed: "Delayed",
  stale: "Missing",
  no_data: "No data",
};

/** V7 Data quality / feed status (ANOM-04, VIEW-12): is every ward's data arriving? */
export function FeedStatus() {
  const { asOf, alertsVersion } = useApp();
  const feed = useFetch((signal) => api.feed(asOf, signal), [asOf]);
  const gaps = useFetch(
    (signal) => api.alerts({ as_of: asOf, type: "data_gap", include_resolved: true }, signal),
    [asOf, alertsVersion],
  );

  return (
    <>
      <section className="ward-head">
        <div>
          <p className="eyebrow">Lab</p>
          <h1>Feed status</h1>
          <p className="ward-sub">Samples received per ward, last 8 weeks · as of {fmtDate(asOf)}</p>
        </div>
      </section>

      {feed.error && <p className="error">Could not load the feed status: {feed.error}</p>}
      {feed.data && (
        <div className={`card ${feed.loading ? "is-loading" : ""}`}>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Ward</th>
                  <th>Status</th>
                  <th>Last sample</th>
                  <th>Usual / day</th>
                  <th>Last 7 days</th>
                  <th>Samples per day, last 8 weeks</th>
                </tr>
              </thead>
              <tbody>
                {feed.data.wards.map((w) => (
                  <tr key={w.ward_code}>
                    <td>
                      <span className="mono">{w.ward_code}</span> <span className="muted">{w.ward_en}</span>
                    </td>
                    <td>
                      <span className={`fresh-pill fresh-${w.status}`}>{STATUS_TEXT[w.status]}</span>
                    </td>
                    <td className="nowrap">{daysAgo(w.days_since_last)}</td>
                    <td className="mono">{w.samples_per_day}</td>
                    <td className="mono">
                      {w.last_week}
                      {w.expected_week !== null && <span className="muted"> / ~{Math.round(w.expected_week)}</span>}
                    </td>
                    <td>
                      <Spark ward={w} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small table-foot">
            Status uses each ward's own sample rate: a silence is flagged when it would be very unlikely by chance
            (busy wards after a day, ICU after several). "Last 7 days" shows received / expected.
          </p>
        </div>
      )}

      <h2 className="section-title">Data-gap alerts (last 90 days)</h2>
      {gaps.data && gaps.data.alerts.length === 0 && <p className="muted">No data gaps in the last 90 days.</p>}
      {gaps.data && gaps.data.alerts.length > 0 && <AlertList alerts={gaps.data.alerts} />}
    </>
  );
}

/** Daily sample counts as a tiny bar strip; empty days are marked in red. */
function Spark({ ward }: { ward: FeedWard }) {
  const counts = ward.daily.counts;
  const max = Math.max(1, ...counts);
  const W = 224;
  const H = 28;
  const bw = W / counts.length;
  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={`Daily samples for ${ward.ward_code}`}>
      {counts.map((c, i) => {
        const h = c === 0 ? 3 : Math.max(2, (c / max) * (H - 2));
        return (
          <rect key={i} x={i * bw} y={H - h} width={Math.max(1, bw - 1)} height={h} className={c === 0 ? "spark-zero" : "spark-bar"}>
            <title>
              {fmtDate(addDays(ward.daily.start, i))}: {c}
            </title>
          </rect>
        );
      })}
    </svg>
  );
}
