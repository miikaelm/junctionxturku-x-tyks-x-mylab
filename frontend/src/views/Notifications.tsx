import { useState } from "react";
import { api, type Message, type Severity, type Subscription } from "../api/client";
import { fmtDate } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";

const CHANNEL_TEXT = { webhook: "Webhook (real HTTP POST)", email: "Email (simulated)", teams: "Teams (simulated)" };
const ROLE_TEXT: Record<string, string> = {
  clinician: "Clinician",
  infection_control: "Infection control",
  lab: "Lab & stewardship",
  system: "Other system",
};

/** Who gets told what, and how (NOTIF-03, NOTIF-05, API-04): subscriptions by role and ward,
 *  the messages they got as of the time cursor, live webhook deliveries and the digest. */
export function Notifications() {
  const { asOf, meta, alertsVersion } = useApp();
  const [version, setVersion] = useState(0);
  const [days, setDays] = useState(7);
  const [only, setOnly] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [period, setPeriod] = useState<"week" | "month">("week");
  const subs = useFetch((signal) => api.subscriptions(signal), [version]);
  const msgs = useFetch(
    (signal) => api.notifications({ as_of: asOf, days, subscription: only || undefined }, signal),
    [asOf, days, only, version, alertsVersion, meta.data_version],
  );
  const live = useFetch((signal) => api.deliveries(signal), [version, meta.data_version]);
  const digest = useFetch((signal) => api.digest({ as_of: asOf, period }, signal), [asOf, period, meta.data_version]);

  const save = async (s: Subscription) => {
    await api.saveSubscription(s);
    setEditing(null);
    setVersion((v) => v + 1);
  };

  return (
    <>
      <section className="ward-head">
        <div>
          <p className="eyebrow">Settings · notifications</p>
          <h1>Who gets told what</h1>
          <p className="ward-sub">
            Alerts live in AEI (overview, alert list); these settings only decide who is also told outside it, by role
            and ward, on the channels people already use · as of {fmtDate(asOf)}
          </p>
        </div>
      </section>

      <section className="card pad">
        <h2>Subscriptions</h2>
        <div className="table-scroll">
          <table className="table compact">
            <thead>
              <tr>
                <th>Who</th>
                <th>Channel</th>
                <th>Wards</th>
                <th>Gets</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(subs.data?.subscriptions ?? []).map((s) =>
                editing === s.id ? (
                  <tr key={s.id}>
                    <td colSpan={5}>
                      <SubscriptionForm sub={s} onSave={save} onCancel={() => setEditing(null)} />
                    </td>
                  </tr>
                ) : (
                  <tr key={s.id}>
                    <td>
                      <strong>{s.name}</strong>
                      <span className="block muted small">{ROLE_TEXT[s.role]}</span>
                    </td>
                    <td>
                      {CHANNEL_TEXT[s.channel]}
                      <span className="block muted small mono">{s.target}</span>
                    </td>
                    <td>{s.wards ? s.wards.join(", ") : "All wards"}</td>
                    <td className="small">
                      {s.events.includes("alert") &&
                        `${s.types ? s.types.join(", ") : "All"} alerts, ${s.min_severity} and above${s.include_routine ? ", incl. known carriers sampled" : ""}`}
                      {s.events.includes("carrier_flag") && <span className="block">New carrier flags</span>}
                      {s.events.includes("digest") && <span className="block">Weekly digest (Mondays)</span>}
                    </td>
                    <td className="nowrap">
                      <button type="button" className="link-btn" onClick={() => setEditing(s.id)}>
                        Edit
                      </button>{" "}
                      <button
                        type="button"
                        className="link-btn"
                        onClick={() => api.testSubscription(s.id).then(() => setVersion((v) => v + 1))}
                      >
                        Send test
                      </button>
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
        <p className="muted small table-foot">
          A ward doctor gets their own ward's alerts; infection control gets every ward but not the routine "known
          carrier sampled" alerts; the patient record system receives carrier flags by webhook.{" "}
          <button type="button" className="link-btn" onClick={() => api.resetSubscriptions().then(() => setVersion((v) => v + 1))}>
            Reset to the demo defaults
          </button>
        </p>
      </section>

      <section className="card pad">
        <div className="therapy-head">
          <h2>Messages sent</h2>
          <div className="filters-patient">
            <label className="field">
              <span className="field-label">Recipient</span>
              <select value={only} onChange={(e) => setOnly(e.target.value)}>
                <option value="">Everyone</option>
                {(subs.data?.subscriptions ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Days</span>
              <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
                {[1, 7, 14, 28].map((d) => (
                  <option key={d} value={d}>
                    Last {d} day{d > 1 ? "s" : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <p className="muted small">
          What each subscription received in the days up to the time cursor, from the same alerts as the inbox, so replay
          shows what was sent when.
        </p>
        {msgs.data && msgs.data.messages.length === 0 && <p className="empty">No messages in this period.</p>}
        <ul className="msg-list">
          {(msgs.data?.messages ?? []).slice(0, 80).map((m, i) => (
            <MessageItem key={`${m.subscription}-${m.ref}-${m.event}-${i}`} m={m} />
          ))}
        </ul>
        {(msgs.data?.messages.length ?? 0) > 80 && (
          <p className="muted small">and {msgs.data!.messages.length - 80} more (narrow by recipient)</p>
        )}
      </section>

      <div className="detail-grid">
        <section className="card pad">
          <h2>Live deliveries</h2>
          <p className="muted small">
            Sent when new lab data arrives (Feed status → receive data, or POST /api/ingest). Webhooks are real HTTP
            posts; the mock patient record receives them.
          </p>
          {(live.data?.deliveries ?? []).length === 0 ? (
            <p className="muted">Nothing sent since the server started.</p>
          ) : (
            <ul className="history">
              {live.data!.deliveries.slice(0, 30).map((d, i) => (
                <li key={i}>
                  <span className="mono small">{d.at.slice(11)}</span> {d.name ?? ""} · {d.subject ?? ""}{" "}
                  <span className={`small ${d.status.startsWith("failed") || d.status.startsWith("error") ? "error-text" : "muted"}`}>
                    {d.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <button type="button" className="link-btn" onClick={() => setVersion((v) => v + 1)}>
            Refresh
          </button>
        </section>
        <section className="card pad">
          <div className="therapy-head">
            <h2>Digest</h2>
            <select value={period} onChange={(e) => setPeriod(e.target.value as "week" | "month")}>
              <option value="week">Last 7 days</option>
              <option value="month">Last 30 days</option>
            </select>
          </div>
          {digest.data ? <pre className="digest">{digest.data.text}</pre> : <p className="muted">Loading…</p>}
          {digest.data && digest.data.alerts.length > 0 && (
            <ul className="history small">
              {digest.data.alerts.slice(0, 6).map((a) => (
                <li key={a.id}>
                  <a href={href({ view: "alert", id: a.id })}>{a.title}</a>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}

function MessageItem({ m }: { m: Message }) {
  const body =
    typeof m.body === "string" ? m.body : JSON.stringify(m.body, null, 2);
  return (
    <li className={`msg msg-${m.channel}`}>
      <details>
        <summary>
          <span className="mono small">{m.day}</span> <span className="msg-channel">{m.channel}</span>{" "}
          <strong>{m.name}</strong> · {m.subject}
        </summary>
        <p className="muted small">To: {m.target}</p>
        <pre className="digest">{body}</pre>
      </details>
    </li>
  );
}

function SubscriptionForm({
  sub,
  onSave,
  onCancel,
}: {
  sub: Subscription;
  onSave: (s: Subscription) => void;
  onCancel: () => void;
}) {
  const { meta } = useApp();
  const [s, set] = useState(sub);
  const toggleWard = (w: string) => {
    const cur = s.wards ?? [];
    const next = cur.includes(w) ? cur.filter((x) => x !== w) : [...cur, w];
    set({ ...s, wards: next.length ? next : null });
  };
  const toggleEvent = (e: Subscription["events"][number]) =>
    set({ ...s, events: s.events.includes(e) ? s.events.filter((x) => x !== e) : [...s.events, e] });
  return (
    <form
      className="sub-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(s);
      }}
    >
      <label className="field">
        <span className="field-label">Name</span>
        <input value={s.name} onChange={(e) => set({ ...s, name: e.target.value })} />
      </label>
      <label className="field">
        <span className="field-label">Channel</span>
        <select value={s.channel} onChange={(e) => set({ ...s, channel: e.target.value as Subscription["channel"] })}>
          {Object.entries(CHANNEL_TEXT).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span className="field-label">Target</span>
        <input value={s.target} onChange={(e) => set({ ...s, target: e.target.value })} />
      </label>
      <label className="field">
        <span className="field-label">Minimum severity</span>
        <select value={s.min_severity} onChange={(e) => set({ ...s, min_severity: e.target.value as Severity })}>
          {meta.severities.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </label>
      <fieldset className="field">
        <span className="field-label">Wards (none ticked = all)</span>
        <div className="checks">
          {meta.wards.map((w) => (
            <label key={w.ward_code} className="check">
              <input type="checkbox" checked={s.wards?.includes(w.ward_code) ?? false} onChange={() => toggleWard(w.ward_code)} />
              {w.ward_code}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="field">
        <span className="field-label">Gets</span>
        <div className="checks">
          {(["alert", "carrier_flag", "digest"] as const).map((e) => (
            <label key={e} className="check">
              <input type="checkbox" checked={s.events.includes(e)} onChange={() => toggleEvent(e)} />
              {e === "alert" ? "Alerts" : e === "carrier_flag" ? "New carrier flags" : "Weekly digest"}
            </label>
          ))}
          <label className="check">
            <input type="checkbox" checked={s.include_routine} onChange={(e) => set({ ...s, include_routine: e.target.checked })} />
            Known carriers sampled
          </label>
        </div>
      </fieldset>
      <div className="triage-actions">
        <button type="submit" className="btn btn-primary">
          Save
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
