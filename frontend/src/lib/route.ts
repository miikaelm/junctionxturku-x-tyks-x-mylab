import { useEffect, useState } from "react";

/** Minimal hash routing, so views can be linked to and the back button works. */
export type Route =
  | { view: "start" }
  | { view: "ward" }
  | { view: "alerts" }
  | { view: "alert"; id: string }
  | { view: "feed" }
  | { view: "overview" }
  | { view: "trends" }
  | { view: "spread" }
  | { view: "patients" }
  | { view: "patient"; id: string }
  | { view: "notifications" }
  | { view: "ehr"; id?: string };

const SIMPLE = ["start", "feed", "overview", "trends", "spread", "patients", "notifications"] as const;

export function parseHash(hash: string): Route {
  const [view, id] = hash.replace(/^#\/?/, "").split("/");
  const key = id ? decodeURIComponent(id) : undefined;
  if (view === "alerts" && key) return { view: "alert", id: key };
  if (view === "alerts") return { view: "alerts" };
  if (view === "patients" && key) return { view: "patient", id: key };
  if (view === "ehr") return { view: "ehr", id: key };
  if ((SIMPLE as readonly string[]).includes(view)) return { view } as Route;
  return { view: "ward" };
}

export function href(route: Route): string {
  if (route.view === "alert") return `#/alerts/${encodeURIComponent(route.id)}`;
  if (route.view === "patient") return `#/patients/${encodeURIComponent(route.id)}`;
  if (route.view === "ehr") return route.id ? `#/ehr/${encodeURIComponent(route.id)}` : "#/ehr";
  return `#/${route.view}`;
}

export function useHashRoute() {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
