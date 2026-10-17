import type { AlertSummary, Severity, TriageStatus } from "../api/client";
import { fmtDate } from "../lib/format";
import { href } from "../lib/route";

const SEVERITY_TEXT: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
};

export const TRIAGE_TEXT: Record<TriageStatus, string> = {
  new: "New",
  investigating: "Investigating",
  confirmed: "Confirmed",
  dismissed: "Dismissed",
};

export function SeverityPill({ severity }: { severity: Severity }) {
  return <span className={`sev sev-${severity}`}>{SEVERITY_TEXT[severity]}</span>;
}

export function TriagePill({ alert }: { alert: AlertSummary }) {
  const { status, suppressed_by } = alert.triage;
  return (
    <span
      className={`triage triage-${status}`}
      title={suppressed_by ? `Auto-dismissed: repeats dismissed alert ${suppressed_by}` : undefined}
    >
      {TRIAGE_TEXT[status]}
      {suppressed_by ? " (repeat)" : ""}
    </span>
  );
}

/** p-values for people: small ones as "< 0.001", never as a wall of digits. */
export function fmtP(p: number | undefined): string {
  if (p === undefined || p === null) return "–";
  if (p < 0.001) return "< 0.001";
  return p.toFixed(3);
}

/** Compact alert list, used for the ward alert strip (V1) and feed-status view (V7). */
export function AlertList({ alerts, showWard = true }: { alerts: AlertSummary[]; showWard?: boolean }) {
  return (
    <ul className="alert-list">
      {alerts.map((a) => (
        <li key={a.id} className={`alert-item ${a.state === "resolved" ? "is-resolved" : ""}`}>
          <a href={href({ view: "alert", id: a.id })}>
            <SeverityPill severity={a.severity} />
            <span className="alert-item-main">
              <strong>
                {showWard && <span className="mono">{a.ward} · </span>}
                {a.type_label}
              </strong>
              <span>{a.title}</span>
            </span>
            <span className="alert-item-meta muted">
              {a.state === "active" ? `since ${fmtDate(a.first_seen)}` : `resolved ${fmtDate(a.resolved_on!)}`}
            </span>
            <TriagePill alert={a} />
          </a>
        </li>
      ))}
    </ul>
  );
}
