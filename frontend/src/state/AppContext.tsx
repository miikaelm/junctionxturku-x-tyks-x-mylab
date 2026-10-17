import { createContext, useContext } from "react";
import type { AlertCounts, AlertSummary, Meta } from "../api/client";
import type { RoleSetting } from "../lib/roles";

export interface AppState {
  meta: Meta;
  /** Global time cursor (LIVE-01): every view computes as if this day were today. */
  asOf: string;
  setAsOf: (date: string) => void;
  /** Active alerts across all wards at asOf, for the nav badge (NOTIF-02). */
  alertCounts: AlertCounts | null;
  /** Bumped after a triage action so every alert list refetches. */
  alertsVersion: number;
  refreshAlerts: () => void;
  /** Replay playback (LIVE-02): the cursor steps forward on its own while playing. */
  playing: boolean;
  setPlaying: (playing: boolean) => void;
  /** Alerts first raised since replay started stepping forward (LIVE-02). */
  news: AlertSummary[];
  clearNews: () => void;
  /** Ask the backend now whether new data arrived (DATA-05), instead of at the next poll. */
  checkForData: () => void;
  /** Who is using the app (VIEW-08): decides the home view, the nav and patient-level data. */
  role: RoleSetting;
  setRole: (role: RoleSetting | null) => void;
}

export const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside AppContext");
  return ctx;
}
