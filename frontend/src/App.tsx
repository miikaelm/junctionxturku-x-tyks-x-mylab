import { useState } from "react";
import { api } from "./api/client";
import { Header } from "./components/Header";
import { useFetch } from "./lib/hooks";
import { AppContext } from "./state/AppContext";
import { MyWard } from "./views/MyWard";

export default function App() {
  const { data: meta, error } = useFetch(() => api.meta(), []);
  const [asOf, setAsOf] = useState<string | null>(null);

  if (error) {
    return (
      <div className="boot">
        <p className="error">Backend unreachable ({error}). Start it with `uv run uvicorn app.main:app`.</p>
      </div>
    );
  }
  if (!meta) return <div className="boot">Loading…</div>;

  return (
    <AppContext.Provider value={{ meta, asOf: asOf ?? meta.default_as_of, setAsOf }}>
      <Header />
      <main className="page">
        <MyWard />
      </main>
    </AppContext.Provider>
  );
}
