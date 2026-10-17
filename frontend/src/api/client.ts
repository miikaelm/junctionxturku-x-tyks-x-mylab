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
  alert_types: { key: AlertType; label: string; severity: Severity }[];
  severities: Severity[];
  triage_statuses: TriageStatus[];
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

export interface FeedWard extends WardFreshness {
  daily: { start: string; counts: number[] };
  last_week: number;
  expected_week: number | null;
}

export interface Feed {
  as_of: string;
  wards: FeedWard[];
}

// ---------- Alerts (slice 2) ----------

export type AlertType = "sentinel" | "cluster" | "rate_shift" | "novelty" | "data_gap";
export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type TriageStatus = "new" | "investigating" | "confirmed" | "dismissed";

/** Why an alert fired (ANOM-06). Fields depend on the alert type. */
export interface Evidence {
  method: string;
  p_value?: number;
  q_value?: number;
  observed?: number | Estimate;
  expected?: number | Estimate;
  window?: { start: string; end: string };
  baseline?: { start: string; end: string; cases?: number; days?: number };
  [key: string]: unknown;
}

export interface AlertSummary {
  id: string;
  type: AlertType;
  type_label: string;
  severity: Severity;
  ward: string;
  ward_en: string;
  subject: string;
  title: string;
  first_seen: string;
  last_seen: string;
  firings: number;
  state: "active" | "resolved";
  resolved_on: string | null;
  triage: { status: TriageStatus; note: string; as_of: string | null; suppressed_by: string | null };
  evidence: Evidence;
}

export interface AlertCounts {
  active: number;
  new: number;
  by_severity: Partial<Record<Severity, number>>;
}

export interface AlertList {
  as_of: string;
  counts: AlertCounts;
  alerts: AlertSummary[];
}

export interface CaseRow {
  isolate_id: string;
  date: string;
  patient_id: string;
  sex: "F" | "M";
  age: number;
  ward: string;
  specimen: Specimen;
  organism: string;
  phenotypes: string[];
  days_since_admission: number | null;
  hospital_acquired: boolean;
  resistant: string[];
  tested: number;
  highlight: boolean | null;
}

export interface TimelinePoint extends Partial<Estimate> {
  start: string;
  end: string;
  value?: number;
}

export interface AlertTimeline {
  kind: "counts" | "rate";
  label: string;
  unit: "day" | "week" | "4 weeks";
  expected: number | null;
  points: TimelinePoint[];
}

export interface TriageEntry {
  status: TriageStatus;
  as_of: string;
  note: string;
  at: string;
}

export interface AlertDetail extends AlertSummary {
  as_of: string;
  trigger: { day: string; title: string; evidence: Evidence };
  history: { day: string; title: string; p_value?: number; q_value?: number }[];
  cases: CaseRow[];
  timeline: AlertTimeline;
  triage_history: TriageEntry[];
}

export interface AlertQuery {
  location?: string;
  type?: AlertType;
  include_resolved?: boolean;
  as_of: string;
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

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
  feed: (as_of: string, signal?: AbortSignal) => get<Feed>("/feed", { as_of }, signal),
  alerts: (q: AlertQuery, signal?: AbortSignal) => get<AlertList>("/alerts", { ...q }, signal),
  alert: (id: string, as_of: string, signal?: AbortSignal) =>
    get<AlertDetail>(`/alerts/${encodeURIComponent(id)}`, { as_of }, signal),
  triage: (id: string, status: TriageStatus, as_of: string, note = "") =>
    post<TriageEntry>(`/alerts/${encodeURIComponent(id)}/triage`, { status, note, as_of }),
};
