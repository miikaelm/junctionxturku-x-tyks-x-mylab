import { useState } from "react";
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
  const { asOf, alertsVersion, meta } = useApp();
  const feed = useFetch((signal) => api.feed(asOf, signal), [asOf, meta.data_version]);
  const gaps = useFetch(
    (signal) => api.alerts({ as_of: asOf, type: "data_gap", include_resolved: true }, signal),
    [asOf, alertsVersion, meta.data_version],
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

      <LabFeed />

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

/** Incremental ingestion (DATA-05): what has been received, the last batch, and (when the server
 * holds data back) a button that receives the next day as a live lab feed would deliver it. */
function LabFeed() {
  const { meta, checkForData } = useApp();
  const status = useFetch((signal) => api.status(signal), [meta.data_version]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const s = status.data;
  const last = s?.last_ingest;

  const receive = async (days: number) => {
    setBusy(true);
    setErr(null);
    try {
      await api.ingestHeldBack(days);
      checkForData();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!s) return null;
  return (
    <section className="card pad lab-feed">
      <h2>Lab feed</h2>
      <p>
        Data received through <strong>{fmtDate(s.data_end)}</strong> ({s.rows.cultures.toLocaleString("en")} cultures,
        version {s.version}). New results are appended as they arrive; alerts are re-run only from the earliest sample
        date in each batch.
      </p>
      {last && (
        <p className="muted small">
          Last batch {last.at.replace("T", " ")} from {last.source}: {last.rows.cultures} cultures, {last.rows.isolates}{" "}
          isolates, {last.rows.susceptibility} results
          {last.sample_dates && ` sampled ${fmtDate(last.sample_dates.from)}${last.sample_dates.to !== last.sample_dates.from ? ` – ${fmtDate(last.sample_dates.to)}` : ""}`}
          ; recomputed from {last.recomputed_from ? fmtDate(last.recomputed_from) : "–"} in {last.seconds.total} s.
        </p>
      )}
      {s.held_back ? (
        <div className="triage-actions">
          <button type="button" className="btn" disabled={busy} onClick={() => receive(1)}>
            Receive next day
          </button>
          <button type="button" className="btn" disabled={busy} onClick={() => receive(7)}>
            Receive next week
          </button>
          <span className="muted small">
            Simulated feed: {s.held_back.days} days ({fmtDate(s.held_back.from)} – {fmtDate(s.held_back.to)}) held back
            at startup.
          </span>
        </div>
      ) : (
        <p className="muted small">
          Live ingestion: <span className="mono">POST /api/ingest</span> with new rows in the CSV schema. Start the
          server with <span className="mono">AEI_HOLD_BACK_FROM=YYYY-MM-DD</span> to replay the end of the data as a
          live feed.
        </p>
      )}
      {err && <p className="error">{err}</p>}
    </section>
  );
}
