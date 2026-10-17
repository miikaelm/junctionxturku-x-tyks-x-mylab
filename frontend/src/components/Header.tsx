import { TimeCursor } from "./TimeCursor";

export function Header() {
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
        <span className="nav-item active">My Ward</span>
      </nav>
      <TimeCursor />
    </header>
  );
}
