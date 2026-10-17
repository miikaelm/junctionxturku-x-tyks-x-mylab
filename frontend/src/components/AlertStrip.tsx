import { api } from "../api/client";
import { useFetch } from "../lib/hooks";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";
import { AlertList } from "./AlertBits";

/** Active alerts for the selected ward or location, shown on My Ward (V1, NOTIF-02). */
export function AlertStrip({ location }: { location: string }) {
  const { asOf, alertsVersion, meta } = useApp();
  const { data } = useFetch(
    (signal) => api.alerts({ as_of: asOf, location }, signal),
    [asOf, location, alertsVersion, meta.data_version],
  );
  if (!data) return null;
  const open = data.alerts.filter((a) => a.triage.status !== "dismissed");
  const alerts = open.filter((a) => !a.routine);
  const carriers = open.filter((a) => a.routine);
  if (open.length === 0) {
    return <p className="alert-strip-empty muted small">No active alerts here.</p>;
  }
  const isWard = location !== "all" && !["hospital", "primary_care"].includes(location);
  return (
    <section className="alert-strip">
      <p className="alert-strip-head">
        <strong>
          {alerts.length} active alert{alerts.length === 1 ? "" : "s"}
        </strong>{" "}
        <a href={href({ view: "alerts" })}>All alerts →</a>
      </p>
      {alerts.length > 0 && <AlertList alerts={alerts} showWard={!isWard} />}
      {carriers.length > 0 && (
        <details className="alert-strip-routine">
          <summary className="small">
            {carriers.length} known carrier{carriers.length > 1 ? "s" : ""} sampled here recently (contact precautions)
          </summary>
          <AlertList alerts={carriers} showWard={!isWard} />
        </details>
      )}
    </section>
  );
}
