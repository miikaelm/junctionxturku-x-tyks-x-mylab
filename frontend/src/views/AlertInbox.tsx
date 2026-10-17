import { useState } from "react";
import { api, type AlertType } from "../api/client";
import { SeverityPill, TriagePill } from "../components/AlertBits";
import { fmtDate } from "../lib/format";
import { useFetch, useLocalStorage } from "../lib/hooks";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";

/** V3 Alert inbox: every alert as of the time cursor, most urgent first (NOTIF-02). */
export function AlertInbox() {
  const { meta, asOf, alertsVersion } = useApp();
  const [location, setLocation] = useLocalStorage("aei.alerts.location", "all");
  const [type, setType] = useState<AlertType | "">("");
  const [includeResolved, setIncludeResolved] = useState(false);
  const [hideDismissed, setHideDismissed] = useState(true);

  const { data, error, loading } = useFetch(
    (signal) =>
      api.alerts(
        { as_of: asOf, location, type: type || undefined, include_resolved: includeResolved },
        signal,
      ),
    [asOf, location, type, includeResolved, alertsVersion],
  );
  const alerts = (data?.alerts ?? []).filter((a) => !hideDismissed || a.triage.status !== "dismissed");
  const hidden = (data?.alerts.length ?? 0) - alerts.length;

  return (
    <>
      <section className="ward-head">
        <div>
          <p className="eyebrow">Infection control</p>
          <h1>Alerts</h1>
          <p className="ward-sub">
            {data ? `${data.counts.active} active · ${data.counts.new} new` : "…"} · as of {fmtDate(asOf)}
          </p>
        </div>
      </section>

      <div className="filters">
        <div className="filters-patient">
          <label className="field">
            <span className="field-label">Location</span>
            <select value={location} onChange={(e) => setLocation(e.target.value)}>
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
            <span className="field-label">Type</span>
            <select value={type} onChange={(e) => setType(e.target.value as AlertType | "")}>
              <option value="">All types</option>
              {meta.alert_types.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label className="check">
            <input type="checkbox" checked={includeResolved} onChange={(e) => setIncludeResolved(e.target.checked)} />
            Show resolved (last 90 days)
          </label>
          <label className="check">
            <input type="checkbox" checked={hideDismissed} onChange={(e) => setHideDismissed(e.target.checked)} />
            Hide dismissed
          </label>
        </div>
      </div>

      {error && <p className="error">Could not load alerts: {error}</p>}
      {data && (
        <div className={`card ${loading ? "is-loading" : ""}`}>
          {alerts.length === 0 ? (
            <p className="empty">
              No {includeResolved ? "" : "active "}alerts for this selection as of {fmtDate(asOf)}.
            </p>
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Ward</th>
                    <th>Alert</th>
                    <th>First seen</th>
                    <th>Last signal</th>
                    <th>State</th>
                    <th>Triage</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((a) => (
                    <tr key={a.id} className={a.state === "resolved" ? "is-resolved" : ""}>
                      <td>
                        <SeverityPill severity={a.severity} />
                      </td>
                      <td className="mono">{a.ward}</td>
                      <td>
                        <a href={href({ view: "alert", id: a.id })} className="row-link">
                          <strong>{a.type_label}</strong>
                          <span>{a.title}</span>
                        </a>
                      </td>
                      <td className="nowrap">{fmtDate(a.first_seen)}</td>
                      <td className="nowrap">{fmtDate(a.last_seen)}</td>
                      <td>{a.state === "active" ? "Active" : `Resolved ${fmtDate(a.resolved_on!)}`}</td>
                      <td>
                        <TriagePill alert={a} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {hidden > 0 && <p className="muted small table-foot">{hidden} dismissed alert(s) hidden.</p>}
        </div>
      )}
      <p className="muted small note">
        Alerts are raised automatically: sentinel findings (CPE, VRE, carbapenem or vancomycin
        resistance) on the first case; clusters and resistance shifts when a ward's recent numbers
        differ significantly from its own past year (false-discovery-rate controlled); data gaps
        when a ward's feed goes unusually quiet.
      </p>
    </>
  );
}
