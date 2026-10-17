import { useState } from "react";
import type { Meta, Role } from "../api/client";
import { ROLES, type RoleSetting } from "../lib/roles";
import { href, type Route } from "../lib/route";

/** Role-based entry (VIEW-08): choose a role and land on its home view. */
export function RolePicker({
  meta,
  current,
  onPick,
}: {
  meta: Meta;
  current: RoleSetting | null;
  onPick: (r: RoleSetting) => void;
}) {
  const [ward, setWard] = useState(current?.ward ?? meta.wards[0].ward_code);
  const pick = (role: Role) => {
    const setting: RoleSetting = role === "clinician" ? { role, ward } : { role };
    if (role === "clinician") {
      try {
        localStorage.setItem("aei.location", JSON.stringify(ward)); // My Ward opens on it
      } catch {
        // storage unavailable: My Ward falls back to its default
      }
    }
    onPick(setting);
    window.location.hash = href({ view: ROLES[role].home } as Route);
  };

  return (
    <main className="page role-page">
      <section className="ward-head">
        <div>
          <p className="eyebrow">AEI · Antibiotic Efficacy Indicator</p>
          <h1>Who are you?</h1>
          <p className="ward-sub">Each role opens on what it needs most. You can switch at any time from the top bar.</p>
        </div>
      </section>
      <div className="role-grid">
        {(Object.keys(ROLES) as Role[]).map((key) => {
          const r = ROLES[key];
          return (
            <section key={key} className={`card pad role-card ${current?.role === key ? "is-current" : ""}`}>
              <h2>{r.label}</h2>
              <p className="muted small">{r.who}</p>
              <p className="role-question">“{r.question}”</p>
              {key === "clinician" && (
                <label className="field">
                  <span className="field-label">My ward</span>
                  <select value={ward} onChange={(e) => setWard(e.target.value)}>
                    {meta.wards.map((w) => (
                      <option key={w.ward_code} value={w.ward_code}>
                        {w.ward_en} ({w.ward_code})
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <p className="muted small">
                Opens on: {r.nav.find((n) => n.view === r.home)?.label}
                {r.patientLevel ? " · sees patient-level data" : " · aggregates only"}
              </p>
              <button type="button" className="btn btn-primary" onClick={() => pick(key)}>
                Continue as {r.label.toLowerCase()}
              </button>
            </section>
          );
        })}
      </div>
      <p className="muted small note">
        Demo: there is no login. In the hospital the role would come from the user's account (single sign-on).{" "}
        <a href={href({ view: "ehr" })}>Open the mock patient record</a> to see AEI inside another system.
      </p>
    </main>
  );
}
