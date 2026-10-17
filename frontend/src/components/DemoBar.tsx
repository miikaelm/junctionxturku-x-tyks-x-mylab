import { AnimatePresence, motion } from "motion/react";
import { api, type ReplayEvent } from "../api/client";
import { fmtDate } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";
import { SeverityPill } from "./AlertBits";
import { TimeCursor } from "./TimeCursor";

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
 * Demo tools, docked at the bottom (LIVE-01, LIVE-02, LIVE-04, API-05): the as-of date, replay,
 * jump to a past alert, and the mock patient record. None of this is part of real use, where AEI
 * always shows today, so it is kept out of the header and can be hidden.
 */
export function DemoBar({
  settings,
  onSettings,
  open,
  onOpen,
}: {
  settings: ReplaySettings;
  onSettings: (s: ReplaySettings) => void;
  open: boolean;
  onOpen: (open: boolean) => void;
}) {
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

  if (!open) {
    return (
      <button type="button" className={`demo-pill ${atToday ? "" : "is-past"}`} onClick={() => onOpen(true)}>
        <span className="demo-tag">Demo</span>
        {atToday ? "Replay & EHR demo" : `Viewing ${fmtDate(asOf)}`}
        {playing && " · ▶ playing"}
        {news.length > 0 && ` · ${news.length} new`}
      </button>
    );
  }

  return (
    <motion.div
      className="demo"
      role="region"
      aria-label="Demo tools"
      initial={{ y: 40, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <AnimatePresence>
        {news.length > 0 && (
          <motion.div
            className="demo-news"
            role="status"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
          >
            <div className="demo-news-head">
              <strong>
                {news.length} new alert{news.length > 1 ? "s" : ""} while stepping forward
              </strong>
              <button type="button" className="link-btn" onClick={clearNews}>
                Clear
              </button>
            </div>
            <ul>
              {news.slice(0, 4).map((a) => (
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
              {news.length > 4 && <li className="muted small">and {news.length - 4} more in the alert inbox</li>}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="demo-bar">
        <div className="demo-label">
          <span className="demo-tag">Demo only</span>
          <span className="demo-note">Real use always shows today. These tools move time and open a mock patient record.</span>
        </div>

        <TimeCursor />

        <div className="demo-replay">
          <button
            type="button"
            className={`replay-play ${playing ? "on" : ""}`}
            onClick={() => setPlaying(!playing)}
            disabled={atToday && !playing}
            title={atToday ? "Move the date back (or jump to a past alert) to replay from there" : "Step the date forward automatically"}
          >
            {playing ? "❚❚ Pause" : "▶ Replay"}
          </button>
          <label className="replay-field replay-opt">
            Step
            <select value={settings.stepDays} onChange={(e) => onSettings({ ...settings, stepDays: Number(e.target.value) })}>
              <option value={1}>1 day</option>
              <option value={7}>1 week</option>
            </select>
          </label>
          <label className="replay-field replay-opt">
            Speed
            <select value={settings.delayMs} onChange={(e) => onSettings({ ...settings, delayMs: Number(e.target.value) })}>
              {SPEEDS.map((s) => (
                <option key={s.ms} value={s.ms}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label className="check replay-field replay-opt">
            <input
              type="checkbox"
              checked={settings.pauseOnAlert}
              onChange={(e) => onSettings({ ...settings, pauseOnAlert: e.target.checked })}
            />
            Pause on new alert
          </label>
          <label className="replay-field replay-jump">
            <span className="sr-only">Jump to a past alert</span>
            <select value="" onChange={(e) => jump(e.target.value)} disabled={!events.data}>
              <option value="">Jump to a past alert…</option>
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

        <a className="demo-ehr" href={href({ view: "ehr" })} title="AEI's cards inside a mock hospital patient record">
          Open EHR demo →
        </a>
        <button type="button" className="demo-close" onClick={() => onOpen(false)} aria-label="Hide demo tools" title="Hide demo tools">
          ×
        </button>
      </div>
    </motion.div>
  );
}
