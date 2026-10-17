import type { Estimate, Level, Meta } from "../api/client";

export type Tier = "good" | "warn" | "bad" | "none";

/** Traffic-light tier (VIEW-09): green = likely effective, red = high resistance, grey = too few. */
export function tier(e: Estimate | undefined, t: Meta["thresholds"]): Tier {
  if (!e || !e.sufficient || e.pct === null) return "none";
  if (e.pct < t.good_below) return "good";
  if (e.pct < t.warn_below) return "warn";
  return "bad";
}

export function pct(value: number | null): string {
  if (value === null) return "–";
  if (value > 0 && value < 1) return "<1 %";
  return `${Math.round(value)} %`;
}

/** Marker for a fallback level: H = all hospital wards, P = all health centres, A = all. */
export function levelMark(level: Level, location: string): string {
  if (level === "ward") return "";
  if (level === "institution") return location === "primary_care" ? "P" : "H";
  return "A";
}

export function shortOrganism(name: string): string {
  const [genus, ...rest] = name.split(" ");
  return rest.length ? `${genus[0]}. ${rest.join(" ")}` : name;
}

export function fmtDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function daysAgo(n: number | null): string {
  if (n === null) return "never";
  if (n === 0) return "today";
  if (n === 1) return "yesterday";
  return `${n} days ago`;
}
