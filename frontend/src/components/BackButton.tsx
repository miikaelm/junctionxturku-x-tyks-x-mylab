import { href, routeLabel, type Route } from "../lib/route";
import { useApp } from "../state/AppContext";

const FALLBACK: Partial<Record<Route["view"], Route>> = {
  alert: { view: "alerts" },
  patient: { view: "patients" },
};

/**
 * Where "Back" goes: detail pages always get one (to where you came from, else their list);
 * other pages only when you arrived from the overview drill-down or a ward.
 */
export function backTarget(route: Route, prev: Route | null): { to: Route; history: boolean } | null {
  const cameFrom = prev && prev.view !== route.view ? prev : null;
  const fallback = FALLBACK[route.view];
  if (fallback) return cameFrom ? { to: cameFrom, history: true } : { to: fallback, history: false };
  if (cameFrom && (cameFrom.view === "area" || cameFrom.view === "ward")) return { to: cameFrom, history: true };
  return null;
}

/** A clear way back, naming the place it goes to. Uses browser history so scroll and state survive. */
export function BackButton({ to, history }: { to: Route; history: boolean }) {
  const { meta } = useApp();
  const names = { [meta.varha.hospital.key]: meta.varha.hospital.label };
  return (
    <a
      className="back-btn"
      href={href(to)}
      onClick={(e) => {
        if (!history) return;
        e.preventDefault();
        window.history.back();
      }}
    >
      <span aria-hidden>←</span> Back to {routeLabel(to, names)}
    </a>
  );
}
