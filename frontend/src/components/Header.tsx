import { useEffect, useRef } from "react";
import { fmtDate } from "../lib/format";
import { ROLES } from "../lib/roles";
import { href, type Route } from "../lib/route";
import { useApp } from "../state/AppContext";

const VIEW_OF: Partial<Record<Route["view"], Route["view"]>> = { alert: "alerts", patient: "patients", finding: "trends" };

/**
 * Top bar. Clinicians get no badge (UX-06): their ward's alerts are on My Ward itself. The date
 * controls live in the demo bar; a past date is flagged here when that bar is hidden.
 */
export function Header({
  route,
  badge,
  demoOpen,
  onDemo,
}: {
  route: Route;
  badge: number | null;
  demoOpen: boolean;
  onDemo: () => void;
}) {
  const { role, asOf, meta } = useApp();
  const info = ROLES[role.role];
  const past = asOf < meta.default_as_of;
  // Sticky elements below the bar (the overview's level stepper) sit at its height.
  const bar = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = bar.current;
    if (!el) return;
    const ro = new ResizeObserver(() => document.documentElement.style.setProperty("--topbar-h", `${el.offsetHeight}px`));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const view = VIEW_OF[route.view] ?? route.view;
  return (
    <header className="topbar" ref={bar}>
      <a className="brand" href={href(info.home)} title="Home">
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
      </a>
      <nav className="nav">
        {info.nav.map((n) => (
          <a
            key={n.view}
            href={href(n.view === info.home.view ? info.home : ({ view: n.view } as Route))}
            className={`nav-item ${view === n.view ? "active" : ""}`}
          >
            {n.label}
            {n.view === "alerts" && badge ? (
              <span className="nav-badge" title={`${badge} new active alert${badge > 1 ? "s" : ""}`}>
                {badge}
              </span>
            ) : null}
          </a>
        ))}
      </nav>
      {past && !demoOpen && (
        <button type="button" className="asof-chip" onClick={onDemo} title="Showing the data as it was on this date (demo)">
          Viewing {fmtDate(asOf)}
        </button>
      )}
      <div className="role-chip">
        <span className="role-view">
          {info.label} view
          {role.ward ? <span className="mono"> · {role.ward}</span> : ""}
        </span>
        <a className="role-switch" href={href({ view: "start" })}>
          Change role
        </a>
        {info.settings && (
          <a
            href={href({ view: "notifications" })}
            className={`icon-link ${route.view === "notifications" ? "active" : ""}`}
            title="Notification settings: who is told what, and how"
            aria-label="Notification settings"
          >
            <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden>
              <path
                d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
            </svg>
          </a>
        )}
      </div>
    </header>
  );
}
