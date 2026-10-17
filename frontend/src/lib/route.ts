import { useEffect, useState } from "react";

/** Minimal hash routing, so views can be linked to and the back button works. */
export type Route =
  | { view: "ward" }
  | { view: "alerts" }
  | { view: "alert"; id: string }
  | { view: "feed" };

export function parseHash(hash: string): Route {
  const [view, id] = hash.replace(/^#\/?/, "").split("/");
  if (view === "alerts" && id) return { view: "alert", id: decodeURIComponent(id) };
  if (view === "alerts") return { view: "alerts" };
  if (view === "feed") return { view: "feed" };
  return { view: "ward" };
}

export function href(route: Route): string {
  if (route.view === "alert") return `#/alerts/${encodeURIComponent(route.id)}`;
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
