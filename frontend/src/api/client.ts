// Thin client for the backend API (API-01). Vite proxies /api to the FastAPI server in dev.

export interface Health {
  status: string;
  cultures: number;
  data_start: string;
  data_end: string;
}

export interface Ward {
  ward_code: string;
  ward_fi: string;
  ward_en: string;
  ward_type: "in" | "out";
  institution: "hospital" | "primary_care";
}

export interface Meta {
  data_start: string;
  data_end: string;
  default_as_of: string;
  wards: Ward[];
  locations: { code: string; label: string; level: "institution" | "all" }[];
  specimens: Specimen[];
  organisms: string[];
  age_bands: string[];
  thresholds: { min_isolates: number; good_below: number; warn_below: number; ci_level: number };
}

export type Specimen = "urine" | "blood" | "wound";
export type Level = "ward" | "institution" | "all";

export interface Estimate {
  n: number;
  r: number;
  pct: number | null;
  ci_low: number;
  ci_high: number;
  sufficient: boolean;
}

export interface WindowCell {
  levels: Estimate[]; // one per level in Antibiogram.levels, most specific first
  shown: number | null; // index of the most specific level with enough isolates
}

export interface Cell {
  intrinsic: boolean;
  recent: WindowCell;
  annual: WindowCell;
  headline: "recent" | "annual" | null;
}

export interface OrganismRow {
  organism: string;
  isolates: { recent: number[]; annual: number[] };
  share_annual: number;
  cells: Record<string, Cell | null>;
}

export interface Antibiotic {
  code: string;
  name: string;
  name_fi: string;
  class: string;
  reported_for: string;
}

export interface TimeWindow {
  key: "recent" | "annual";
  label: string;
  start: string;
  end: string;
  days: number;
}

export interface Antibiogram {
  as_of: string;
  scope: { location: string; level: Level; label: string; specimen: Specimen };
  levels: { level: Level; location: string; label: string }[];
  windows: TimeWindow[];
  antibiotics: Antibiotic[];
  organisms: OrganismRow[];
}

export interface WardFreshness {
  ward_code: string;
  ward_en: string;
  last_sample: string | null;
  days_since_last: number | null;
  samples_per_day: number | null;
  p_silence: number | null;
  status: "ok" | "delayed" | "stale" | "no_data";
}

export interface Freshness {
  as_of: string;
  wards: WardFreshness[];
}

export interface AntibiogramQuery {
  location: string;
  specimen: Specimen;
  sex?: "F" | "M";
  age_band?: string;
  hospital_acquired?: boolean;
  as_of?: string;
}

type Params = Record<string, string | number | boolean | undefined>;

async function get<T>(path: string, params: Params = {}, signal?: AbortSignal): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) qs.set(k, String(v));
  const res = await fetch(`/api${path}${qs.size ? `?${qs}` : ""}`, { signal });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<Health>("/health"),
  meta: () => get<Meta>("/meta"),
  antibiogram: (q: AntibiogramQuery, signal?: AbortSignal) =>
    get<Antibiogram>("/antibiogram", { ...q }, signal),
  freshness: (as_of: string, signal?: AbortSignal) =>
    get<Freshness>("/freshness", { as_of }, signal),
};
