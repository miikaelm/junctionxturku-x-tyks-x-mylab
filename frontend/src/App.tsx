import { useState } from "react";
import { api } from "./api/client";
import { Header } from "./components/Header";
import { useFetch } from "./lib/hooks";
import { useHashRoute } from "./lib/route";
import { AppContext } from "./state/AppContext";
import { AlertDetailView } from "./views/AlertDetail";
import { AlertInbox } from "./views/AlertInbox";
import { FeedStatus } from "./views/FeedStatus";
import { MyWard } from "./views/MyWard";

export default function App() {
  const { data: meta, error } = useFetch(() => api.meta(), []);
  const [asOfState, setAsOf] = useState<string | null>(null);
  const [alertsVersion, setAlertsVersion] = useState(0);
  const route = useHashRoute();
  const asOf = asOfState ?? meta?.default_as_of ?? null;
  const alerts = useFetch(
    (signal) => (asOf ? api.alerts({ as_of: asOf }, signal) : Promise.resolve(null)),
    [asOf, alertsVersion],
  );

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
      }}
    >
      <Header route={route} />
      <main className="page">
        {route.view === "ward" && <MyWard />}
        {route.view === "alerts" && <AlertInbox />}
        {route.view === "alert" && <AlertDetailView id={route.id} />}
        {route.view === "feed" && <FeedStatus />}
      </main>
    </AppContext.Provider>
  );
}
