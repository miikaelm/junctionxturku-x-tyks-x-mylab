import { ROLES } from "../lib/roles";
import { href, type Route } from "../lib/route";
import { useApp } from "../state/AppContext";
import { TimeCursor } from "./TimeCursor";

const VIEW_OF: Partial<Record<Route["view"], Route["view"]>> = { alert: "alerts", patient: "patients" };

export function Header({ route, badge }: { route: Route; badge: number }) {
  const { role } = useApp();
  const info = ROLES[role.role];
  const view = VIEW_OF[route.view] ?? route.view;
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" aria-hidden>
          <svg viewBox="0 0 24 24" width="18" height="18">
            <path
              d="M12 3 4 6.5v5.2c0 4.6 3.4 8.4 8 9.3 4.6-.9 8-4.7 8-9.3V6.5L12 3Z"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            <path d="m8.5 12 2.4 2.4 4.6-4.8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <span className="brand-name">AEI</span>
        <span className="brand-sub">Antibiotic Efficacy Indicator</span>
      </div>
      <nav className="nav">
        {info.nav.map((n) => (
          <a key={n.view} href={href({ view: n.view } as Route)} className={`nav-item ${view === n.view ? "active" : ""}`}>
            {n.label}
            {n.view === "alerts" && badge > 0 ? (
              <span className="nav-badge" title={`${badge} new active alert${badge > 1 ? "s" : ""}`}>
                {badge}
              </span>
            ) : null}
          </a>
        ))}
      </nav>
      <div className="role-chip">
        <a href={href({ view: "start" })} title="Switch role">
          {info.label}
          {role.ward ? ` · ${role.ward}` : ""}
        </a>
        <a href={href({ view: "ehr" })} className="muted small" title="AEI inside a mock hospital patient record (demo)">
          EHR demo
        </a>
      </div>
      <TimeCursor />
    </header>
  );
}
