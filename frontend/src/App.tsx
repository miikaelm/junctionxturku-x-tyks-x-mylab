import { useEffect, useRef, useState } from "react";
import { api, type AlertList, type AlertSummary } from "./api/client";
import { Header } from "./components/Header";
import { ReplayBar, type ReplaySettings } from "./components/ReplayBar";
import { addDays } from "./lib/format";
import { useFetch, useIdle, useLocalStorage } from "./lib/hooks";
import { useHashRoute } from "./lib/route";
import { AppContext } from "./state/AppContext";
import { AlertDetailView } from "./views/AlertDetail";
import { AlertInbox } from "./views/AlertInbox";
import { FeedStatus } from "./views/FeedStatus";
import { MyWard } from "./views/MyWard";
import { Overview } from "./views/Overview";
import { Trends } from "./views/Trends";

const STATUS_POLL_MS = 10_000;
const MAX_NEWS_STEP_DAYS = 31;

export default function App() {
  const [metaVersion, setMetaVersion] = useState(0);
  const { data: meta, error } = useFetch(() => api.meta(), [metaVersion]);
  const [asOfState, setAsOf] = useState<string | null>(null);
  const [alertsVersion, setAlertsVersion] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [replay, setReplay] = useLocalStorage<ReplaySettings>("aei.replay", {
    stepDays: 1,
    delayMs: 700,
    pauseOnAlert: true,
  });
  const [news, setNews] = useState<AlertSummary[]>([]);
  const route = useHashRoute();
  const asOf = asOfState ?? meta?.default_as_of ?? null;
  const alerts = useFetch(
    (signal) => (asOf ? api.alerts({ as_of: asOf }, signal) : Promise.resolve(null)),
    [asOf, alertsVersion, meta?.data_version],
  );

  // New alerts as the cursor moves forward (LIVE-02): alerts first raised after the previous
  // as-of, up to this one. Moving backwards starts over.
  const prev = useRef<AlertList | null>(null);
  useEffect(() => {
    const cur = alerts.data;
    if (!cur) return;
    const before = prev.current;
    prev.current = cur;
    if (!before) return;
    if (cur.as_of < before.as_of || cur.as_of > addDays(before.as_of, MAX_NEWS_STEP_DAYS)) {
      setNews([]); // a jump, not a step: everything would be "new"
      return;
    }
    const fresh = cur.alerts.filter(
      (a) => a.first_seen > before.as_of && a.first_seen <= cur.as_of && a.triage.status !== "dismissed",
    );
    if (fresh.length === 0) return;
    setNews((n) => [...fresh, ...n.filter((x) => !fresh.some((f) => f.id === x.id))]);
    if (playing && replay.pauseOnAlert) setPlaying(false);
  }, [alerts.data]); // eslint-disable-line react-hooks/exhaustive-deps

  // Playback: step once every open view has loaded the previous step, so the backend sets the
  // pace and requests never pile up.
  const idle = useIdle();
  useEffect(() => {
    if (!playing || !meta || !asOf || !idle) return;
    if (asOf >= meta.default_as_of) {
      setPlaying(false);
      return;
    }
    const t = window.setTimeout(() => {
      const next = addDays(asOf, replay.stepDays);
      setAsOf(next > meta.default_as_of ? meta.default_as_of : next);
    }, replay.delayMs);
    return () => window.clearTimeout(t);
  }, [playing, asOf, idle, meta, replay.stepDays, replay.delayMs]);

  // New data (DATA-05): poll the data version; when it changes, reload the code tables. A
  // cursor that was on "today" moves to the new today.
  const [pollNow, setPollNow] = useState(0);
  useEffect(() => {
    if (!meta) return;
    const check = () =>
      api
        .status()
        .then((s) => {
          if (s.version === meta.data_version) return;
          if (asOfState === meta.default_as_of) setAsOf(null);
          setMetaVersion((v) => v + 1);
        })
        .catch(() => undefined);
    if (pollNow) check();
    const t = window.setInterval(check, STATUS_POLL_MS);
    return () => window.clearInterval(t);
  }, [meta, asOfState, pollNow]);

  if (error) {
    return (
      <div className="boot">
        <p className="error">Backend unreachable ({error}). Start it with `uv run uvicorn app.main:app`.</p>
      </div>
    );
  }
  if (!meta || !asOf) return <div className="boot">Loading…</div>;

  return (
    <AppContext.Provider
      value={{
        meta,
        asOf,
        setAsOf,
        alertCounts: alerts.data?.counts ?? null,
        alertsVersion,
        refreshAlerts: () => setAlertsVersion((v) => v + 1),
        playing,
        setPlaying,
        news,
        clearNews: () => setNews([]),
        checkForData: () => setPollNow((v) => v + 1),
      }}
    >
      <Header route={route} />
      <ReplayBar settings={replay} onSettings={setReplay} />
      <main className="page">
        {route.view === "ward" && <MyWard />}
        {route.view === "alerts" && <AlertInbox />}
        {route.view === "alert" && <AlertDetailView id={route.id} />}
        {route.view === "overview" && <Overview />}
        {route.view === "trends" && <Trends />}
        {route.view === "feed" && <FeedStatus />}
      </main>
    </AppContext.Provider>
  );
}
