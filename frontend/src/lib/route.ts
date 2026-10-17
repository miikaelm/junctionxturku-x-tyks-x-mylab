import { useEffect, useState } from "react";

/** Minimal hash routing, so views can be linked to and the back button works. */
export type Route =
  | { view: "start" }
  | { view: "ward"; id?: string }
  | { view: "area"; id?: string }
  | { view: "alerts" }
  | { view: "alert"; id: string }
  | { view: "feed" }
  | { view: "heatmap" }
  | { view: "trends" }
  | { view: "spread" }
  | { view: "patients" }
  | { view: "patient"; id: string }
  | { view: "notifications" }
  | { view: "ehr"; id?: string };

const SIMPLE = ["start", "feed", "heatmap", "trends", "spread", "patients", "notifications"] as const;

export function parseHash(hash: string): Route {
  const [view, id] = hash.replace(/^#\/?/, "").split("/");
  const key = id ? decodeURIComponent(id) : undefined;
  if (view === "alerts" && key) return { view: "alert", id: key };
  if (view === "alerts") return { view: "alerts" };
  if (view === "patients" && key) return { view: "patient", id: key };
  if (view === "ehr") return { view: "ehr", id: key };
  if (view === "area") return { view: "area", id: key };
  if (view === "overview") return { view: "area" }; // the old name of the drill-down's place
  if (view === "ward") return { view: "ward", id: key };
  if ((SIMPLE as readonly string[]).includes(view)) return { view } as Route;
  return { view: "ward" };
}

export function href(route: Route): string {
  if (route.view === "alert") return `#/alerts/${encodeURIComponent(route.id)}`;
  if (route.view === "patient") return `#/patients/${encodeURIComponent(route.id)}`;
  if ((route.view === "ehr" || route.view === "area" || route.view === "ward") && route.id) {
    return `#/${route.view}/${encodeURIComponent(route.id)}`;
  }
  return `#/${route.view}`;
}

/**
 * The current route and the one before it. A small stack mirrors the browser history, so a back
 * step pops instead of pushing and "Back to …" keeps pointing at the right place.
 */
export function useHashRoute(): { route: Route; prev: Route | null } {
  const [stack, setStack] = useState(() => [window.location.hash]);
  useEffect(() => {
    const onChange = () =>
      setStack((s) => {
        const h = window.location.hash;
        if (h === s[s.length - 1]) return s;
        if (h === s[s.length - 2]) return s.slice(0, -1);
        return [...s.slice(-30), h];
      });
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return {
    route: parseHash(stack[stack.length - 1]),
    prev: stack.length > 1 ? parseHash(stack[stack.length - 2]) : null,
  };
}

const LABELS: Partial<Record<Route["view"], string>> = {
  alerts: "all alerts",
  alert: "the alert",
  heatmap: "the heatmap",
  trends: "trends",
  feed: "the lab feed",
  spread: "spread",
  patients: "known carriers",
  patient: "the patient",
  notifications: "settings",
};

/** "Back to …" text for a route; area ids are institution keys or ward codes. */
export function routeLabel(route: Route, names: Record<string, string> = {}): string {
  if (route.view === "area") return `${route.id ? (names[route.id] ?? route.id) : "Varha"} overview`;
  if (route.view === "ward") return route.id ? `ward ${route.id}` : "my ward";
  return LABELS[route.view] ?? "the previous page";
}
