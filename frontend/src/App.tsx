import { useEffect, useRef, useState } from "react";
import { api, type AlertList, type AlertSummary } from "./api/client";
import { BackButton, backTarget } from "./components/BackButton";
import { DemoBar, type ReplaySettings } from "./components/DemoBar";
import { Header } from "./components/Header";
import { addDays } from "./lib/format";
import { useFetch, useIdle, useLocalStorage } from "./lib/hooks";
import type { RoleSetting } from "./lib/roles";
import { useHashRoute } from "./lib/route";
import { AppContext } from "./state/AppContext";
import { AlertDetailView } from "./views/AlertDetail";
import { Area } from "./views/Area";
import { AlertInbox } from "./views/AlertInbox";
import { FeedStatus } from "./views/FeedStatus";
import { MockEhr } from "./views/MockEhr";
import { MyWard } from "./views/MyWard";
import { Notifications } from "./views/Notifications";
import { Heatmap } from "./views/Heatmap";
import { PatientView, Patients } from "./views/Patients";
import { RolePicker } from "./views/RolePicker";
import { Spread } from "./views/Spread";
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
  const [role, setRole] = useLocalStorage<RoleSetting | null>("aei.role", null);
  // Demo tools start open on a desktop, closed on a phone where they would cover the page.
  const [demoOpen, setDemoOpen] = useLocalStorage("aei.demo.open", window.matchMedia("(min-width: 601px)").matches);
  const { route, prev: prevRoute } = useHashRoute();
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
    // Routine alerts (known carriers sampled, ~1 per ward per week) would stop replay every step.
    const fresh = cur.alerts.filter(
      (a) =>
        !a.routine && a.first_seen > before.as_of && a.first_seen <= cur.as_of && a.triage.status !== "dismissed",
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

  // Clinicians get no badge (UX-06): their ward's alerts are part of My Ward. The other roles
  // count new non-routine alerts (NOTIF-03).
  const badge = role?.role === "clinician" ? null : (alerts.data?.counts.new ?? 0);
  const picking = !role || route.view === "start";
  const back = backTarget(route, prevRoute);

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
        role: role ?? { role: "infection_control" },
        setRole,
      }}
    >
      {route.view === "ehr" ? (
        <MockEhr patientId={route.id} />
      ) : picking ? (
        <RolePicker meta={meta} current={role} onPick={setRole} />
      ) : (
        <>
          <Header route={route} badge={badge} demoOpen={demoOpen} onDemo={() => setDemoOpen(true)} />
          <main className={`page ${demoOpen ? "with-demo" : ""}`}>
            {back && <BackButton {...back} />}
            {route.view === "ward" && <MyWard ward={route.id} />}
            {route.view === "area" && <Area id={route.id} />}
            {route.view === "alerts" && <AlertInbox />}
            {route.view === "alert" && <AlertDetailView id={route.id} />}
            {route.view === "heatmap" && <Heatmap />}
            {route.view === "trends" && <Trends />}
            {route.view === "feed" && <FeedStatus />}
            {route.view === "spread" && <Spread />}
            {route.view === "patients" && <Patients />}
            {route.view === "patient" && <PatientView id={route.id} />}
            {route.view === "notifications" && <Notifications />}
          </main>
          <DemoBar settings={replay} onSettings={setReplay} open={demoOpen} onOpen={setDemoOpen} />
        </>
      )}
    </AppContext.Provider>
  );
}
