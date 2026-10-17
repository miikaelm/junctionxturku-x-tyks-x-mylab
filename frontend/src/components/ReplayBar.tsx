import { api, type ReplayEvent } from "../api/client";
import { fmtDate } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";
import { SeverityPill } from "./AlertBits";

export interface ReplaySettings {
  stepDays: number;
  delayMs: number;
  pauseOnAlert: boolean;
}

const SPEEDS = [
  { ms: 1500, label: "Slow" },
  { ms: 700, label: "Normal" },
  { ms: 200, label: "Fast" },
];

/**
 * Replay controls (LIVE-02, LIVE-04): play the data forward from the cursor, jump to just before
 * any past alert, and list the alerts that appear while stepping forward.
 */
export function ReplayBar({ settings, onSettings }: { settings: ReplaySettings; onSettings: (s: ReplaySettings) => void }) {
  const { meta, asOf, setAsOf, playing, setPlaying, news, clearNews } = useApp();
  const events = useFetch((signal) => api.replayEvents(signal), [meta.data_version]);
  const atToday = asOf >= meta.default_as_of;

  const jump = (id: string) => {
    const e = events.data?.events.find((x) => x.id === id);
    if (!e) return;
    clearNews();
    setAsOf(e.replay_from);
    setPlaying(true);
  };

  const byType = new Map<string, ReplayEvent[]>();
  for (const e of events.data?.events ?? []) byType.set(e.type, [...(byType.get(e.type) ?? []), e]);

  return (
    <div className="replay">
      <div className="replay-bar">
        <button
          type="button"
          className={`replay-play ${playing ? "on" : ""}`}
          onClick={() => setPlaying(!playing)}
          disabled={atToday && !playing}
          title={atToday ? "Move the cursor back to replay from there" : "Step the cursor forward automatically"}
        >
          {playing ? "❚❚ Pause" : "▶ Replay"}
        </button>
        <label className="replay-field">
          Step
          <select value={settings.stepDays} onChange={(e) => onSettings({ ...settings, stepDays: Number(e.target.value) })}>
            <option value={1}>1 day</option>
            <option value={7}>1 week</option>
          </select>
        </label>
        <label className="replay-field">
          Speed
          <select value={settings.delayMs} onChange={(e) => onSettings({ ...settings, delayMs: Number(e.target.value) })}>
            {SPEEDS.map((s) => (
              <option key={s.ms} value={s.ms}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label className="check replay-field">
          <input
            type="checkbox"
            checked={settings.pauseOnAlert}
            onChange={(e) => onSettings({ ...settings, pauseOnAlert: e.target.checked })}
          />
          Pause on new alert
        </label>
        <label className="replay-field replay-jump">
          Jump to
          <select value="" onChange={(e) => jump(e.target.value)} disabled={!events.data}>
            <option value="">a past alert… (starts a week before it)</option>
            {meta.alert_types
              .filter((t) => byType.has(t.key))
              .map((t) => (
                <optgroup key={t.key} label={`${t.label} (${byType.get(t.key)!.length})`}>
                  {byType.get(t.key)!.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.first_seen} · {e.wards.join(", ")} · {e.title}
                    </option>
                  ))}
                </optgroup>
              ))}
          </select>
        </label>
      </div>
      {news.length > 0 && (
        <div className="replay-news" role="status">
          <div className="replay-news-head">
            <strong>
              {news.length} new alert{news.length > 1 ? "s" : ""} while stepping forward
            </strong>
            <button type="button" className="link-btn" onClick={clearNews}>
              Clear
            </button>
          </div>
          <ul>
            {news.slice(0, 5).map((a) => (
              <li key={a.id}>
                <SeverityPill severity={a.severity} />{" "}
                <a href={href({ view: "alert", id: a.id })}>
                  <span className="mono">{a.wards.join(", ")}</span> {a.type_label}: {a.title}
                </a>{" "}
                <span className="muted small">
                  raised {fmtDate(a.first_seen)}
                  {a.detection_days > 0 && `, ${a.detection_days} d after the first case`}
                </span>
              </li>
            ))}
            {news.length > 5 && <li className="muted small">and {news.length - 5} more in the alert inbox</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
