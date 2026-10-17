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
  data_version: number;
  wards: Ward[];
  locations: { code: string; label: string; level: "institution" | "all" }[];
  specimens: Specimen[];
  organisms: string[];
  age_bands: string[];
  alert_types: { key: AlertType; label: string; severity: Severity; routine: boolean }[];
  severities: Severity[];
  triage_statuses: TriageStatus[];
  home_areas: string[];
  split_dimensions: { key: SplitBy; label: string }[];
  phenotypes: string[];
  key_rates: { specimen: Specimen; organism: string; antibiotic: string; antibiotic_name: string }[];
  tested_pairs: [string, string][];
  intrinsic: Record<string, string[]>;
  antibiotics: { code: string; name: string; reported_for: string }[];
  infections: { key: Infection; label: string; specimen: Specimen }[];
  thresholds: {
    min_isolates: number;
    good_below: number;
    warn_below: number;
    ci_level: number;
    empirical_pct: number;
    coverage_good: number;
    coverage_warn: number;
  };
}

export type Infection = "uti" | "bloodstream" | "wound";

export type SplitBy = "sex" | "age_band" | "hospital_acquired" | "ward_type" | "home_area";

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

export interface SubRow {
  value: string | boolean;
  label: string;
  isolates: { recent: number[]; annual: number[] };
  cells: Record<string, Cell | null>;
}

export interface OrganismRow {
  organism: string;
  isolates: { recent: number[]; annual: number[] };
  share_annual: number;
  cells: Record<string, Cell | null>;
  /** Sub-rows by a patient dimension (STAT-07): default for known splits, or asked for. */
  split?: { by: SplitBy; default: boolean; rows: SubRow[] };
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

export type AlertType =
  | "sentinel"
  | "cluster"
  | "rate_shift"
  | "novelty"
  | "data_gap"
  | "carrier"
  | "multi_ward";
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
  /** The wards the alert concerns: one, or several for a multi-ward signal (ANOM-09). */
  wards: string[];
  /** Routine types (carrier re-appearances) are kept out of the badge and replay pauses. */
  routine: boolean;
  subject: string;
  title: string;
  first_seen: string;
  last_seen: string;
  /** Earliest case behind the first firing (ANOM-07). */
  onset: string;
  detection_days: number;
  firings: number;
  state: "active" | "resolved";
  resolved_on: string | null;
  triage: { status: TriageStatus; note: string; as_of: string | null; suppressed_by: string | null };
  evidence: Evidence;
}

export interface AlertCounts {
  active: number;
  new: number;
  routine: number;
  routine_new: number;
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
  /** Resistance profile key (cluster / multi-ward alerts, ANOM-05). */
  profile?: string;
}

export interface Similarity {
  organism: string;
  other_organisms: number;
  cases: number;
  matching: number;
  share: number;
  dominant: { key: string; label: string; tested: string[] };
  groups: { key: string; label: string; count: number }[];
  mean_agreement: number | null;
  background: { start: string; end: string; isolates: number; matching: number; share: number | null };
  p_value: number | null;
  verdict: "single_strain" | "common_profile" | "mixed";
  text: string;
  method: string;
}

export interface Followup {
  days: number;
  case_patients: number;
  patients: {
    patient_id: string;
    case_date: string;
    case_ward: string;
    seen: { date: string; ward: string; specimen: string }[];
  }[];
  wards: { ward: string; patients: number; first: string }[];
}

export interface CarrierFlag {
  patient_id: string;
  phenotype: string;
  first_positive: string;
  first_ward: string;
  first_organism: string;
  last_positive: string;
  last_ward: string;
  positives: number;
  organisms: string[];
  wards: string[];
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
  similarity: Similarity | null;
  followup: Followup | null;
  patient: { patient_id: string; flags: CarrierFlag[] } | null;
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
  split_by?: SplitBy | "none";
  split_organism?: string;
  as_of?: string;
}

// ---------- Replay, trends, subgroups, overview, ingestion (slice 3) ----------

export interface IngestEntry {
  version: number;
  at: string;
  source: string;
  rows: Record<string, number>;
  sample_dates: { from: string; to: string } | null;
  recomputed_from: string | null;
  seconds: { join: number; total: number };
}

export interface Status {
  version: number;
  data_start: string;
  data_end: string;
  today: string;
  rows: Record<string, number>;
  held_back: { from: string; to: string; days: number; cultures: number } | null;
  last_ingest: IngestEntry | null;
  ingests: number;
}

export interface ReplayEvent {
  id: string;
  type: AlertType;
  type_label: string;
  severity: Severity;
  ward: string;
  wards: string[];
  subject: string;
  title: string;
  onset: string;
  first_seen: string;
  detection_days: number;
  replay_from: string;
  triage: TriageStatus;
}

export interface SubgroupLevel extends Estimate {
  value: string | boolean;
  label: string;
}

export interface SubgroupFinding {
  dimension: string;
  dimension_label: string;
  organism: string;
  antibiotic_code: string;
  antibiotic: string;
  levels: SubgroupLevel[];
  high: string;
  low: string;
  diff_pp: number;
  p_value: number;
  q_value: number;
  text: string;
}

export interface Subgroups {
  as_of: string;
  window: { start: string; end: string; label: string };
  dimensions: { key: string; label: string }[];
  compared: number;
  findings: SubgroupFinding[];
}

export interface TrendStats {
  direction: "up" | "down";
  pp_per_year: number;
  change_pp: number;
  p_value: number;
  q_value: number | null;
  significant: boolean;
  eligible: boolean;
  n: number;
  quarters: number;
}

export interface TrendFinding {
  location: string;
  location_label: string;
  level: Level;
  specimen: Specimen;
  organism: string;
  antibiotic_code: string;
  antibiotic: string;
  last_12m: Estimate;
  prev_12m: Estimate;
  trend?: TrendStats;
}

export interface TrendFindings {
  as_of: string;
  threshold_pct: number;
  tested: number;
  trends: (TrendFinding & { trend: TrendStats })[];
  crossings: (TrendFinding & { direction: "up" | "down"; clearly: boolean })[];
}

export interface TrendPoint extends Estimate {
  label: string;
  start: string;
  end: string;
  fitted: number | null;
}

export interface YearRate extends Estimate {
  year: number;
  start: string;
  end: string;
  partial: boolean;
}

export interface TrendSeries {
  as_of: string;
  scope: { location: string; label: string; specimen: Specimen };
  organism: string;
  antibiotic_code: string;
  antibiotic: string;
  threshold_pct: number;
  points: TrendPoint[];
  trend: TrendStats | null;
  trend_crosses_threshold: string | null;
  years: YearRate[];
  year_vs_year: {
    last: Estimate & { start: string; end: string };
    previous: Estimate & { start: string; end: string };
    p_value: number | null;
    method: string;
  };
}

export interface OverviewMarker {
  id: string;
  type: AlertType;
  type_label: string;
  severity: Severity;
  ward: string;
  wards: string[];
  first_seen: string;
  title: string;
}

export interface OverviewCell extends Partial<Estimate> {
  value?: number;
  alerts?: OverviewMarker[];
}

export interface Overview {
  as_of: string;
  metric: "phenotype" | "rate";
  kind: "count" | "rate";
  bin_days: number;
  bins: { start: string; end: string }[];
  rows: { ward: string; label: string; cells: OverviewCell[] }[];
}

export interface OverviewQuery {
  metric: "phenotype" | "rate";
  phenotype?: string;
  specimen?: Specimen;
  organism?: string;
  antibiotic?: string;
  bins: number;
  bin_days: number;
  as_of: string;
}

// ---------- Patients, spread, therapy, integration (slice 4) ----------

export interface TherapyOrganism {
  organism: string;
  share: number;
  n_isolates: number;
  status: "tested" | "inferred" | "intrinsic" | "not_tested";
  susceptible_pct: number | null;
  n?: number;
  r?: number;
  inferred_from?: string;
}

export interface TherapyAgent {
  code: string;
  name: string;
  class: string;
  coverage_pct: number;
  /** Kept for resistant infections by guidelines (e.g. meropenem). */
  reserve: boolean;
  ci_low: number;
  ci_high: number;
  not_tested_share: number;
  not_tested: string[];
  tier: "good" | "warn" | "bad";
  organisms: TherapyOrganism[];
}

export interface Therapy {
  as_of: string;
  infection: Infection;
  infection_label: string;
  specimen: Specimen;
  window: { start: string; end: string };
  scope: { location: string; label: string };
  used: { location: string; label: string; fell_back: boolean };
  tried: { location: string; label: string; n: number }[];
  isolates: number;
  sufficient: boolean;
  organisms: { organism: string; n: number; share: number }[];
  ranked: TherapyAgent[];
  unranked: TherapyAgent[];
  method: string;
}

export interface TherapyQuery {
  location: string;
  infection: Infection;
  sex?: "F" | "M";
  age_band?: string;
  hospital_acquired?: boolean;
  as_of: string;
}

export interface Carriers {
  as_of: string;
  total: number;
  by_phenotype: Record<string, number>;
  carriers: CarrierFlag[];
}

export interface PatientSample {
  culture_id: string;
  date: string;
  ward: string;
  ward_type: "in" | "out";
  specimen: Specimen;
  result: string;
  admission_date: string | null;
  hospital_acquired: boolean;
  isolates: { isolate_id: string; organism: string; phenotypes: string[]; resistant: string[] }[];
}

export interface Patient {
  as_of: string;
  patient_id: string;
  sex: "F" | "M";
  birth_year: number;
  age: number;
  home_area: string;
  last_ward: string;
  last_sample: string;
  flags: CarrierFlag[];
  samples: PatientSample[];
  alerts: AlertSummary[];
}

export interface SpreadProfile {
  id: string;
  organism: string;
  profile: string;
  label: string;
  count: number;
  wards: string[];
  colour: number | null;
}

export interface Spread {
  as_of: string;
  start: string;
  phenotype: string;
  wards: string[];
  cases: {
    isolate_id: string;
    date: string;
    ward: string;
    patient_id: string;
    organism: string;
    specimen: Specimen;
    profile_id: string;
    hospital_acquired: boolean;
  }[];
  profiles: SpreadProfile[];
  shared: SpreadProfile[];
  paths: { patient_id: string; samples: { date: string; ward: string; case: boolean }[] }[];
  alerts: { id: string; type: AlertType; type_label: string; wards: string[]; first_seen: string; title: string }[];
}

export interface CdsCard {
  uuid: string;
  summary: string;
  indicator: "info" | "warning" | "critical";
  detail: string;
  source: { label: string; url: string };
  links: { label: string; url: string; type: string }[];
}

export interface CdsService {
  hook: string;
  id: string;
  title: string;
  description: string;
}

export type Channel = "webhook" | "email" | "teams";
export type Role = "clinician" | "infection_control" | "lab";

export interface Subscription {
  id: string;
  name: string;
  role: Role | "system";
  channel: Channel;
  target: string;
  wards: string[] | null;
  min_severity: Severity;
  types: AlertType[] | null;
  include_routine: boolean;
  events: ("alert" | "carrier_flag" | "digest")[];
}

export interface Message {
  day: string;
  subscription: string;
  name: string;
  role: string;
  channel: Channel;
  target: string;
  event: string;
  subject: string;
  body: unknown;
  content_type?: string;
  ref: string | null;
}

export interface Delivery {
  at: string;
  day?: string;
  subscription?: string;
  name?: string;
  channel?: Channel;
  target?: string;
  event?: string;
  subject?: string;
  status: string;
}

export interface Digest {
  period: "week" | "month";
  start: string;
  end: string;
  new_alerts: number;
  by_type: Record<string, number>;
  alerts: { id: string; type_label: string; severity: Severity; wards: string[]; title: string; first_seen: string }[];
  carrier_reappearances: number;
  new_carriers: Record<string, number>;
  active_alerts: number;
  trends: { significant: string[]; crossed_up: string[] } | null;
  text: string;
}

type Params = Record<string, string | number | boolean | undefined>;

async function get<T>(path: string, params: Params = {}, signal?: AbortSignal): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) qs.set(k, String(v));
  const res = await fetch(`/api${path}${qs.size ? `?${qs}` : ""}`, { signal });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().then(
      (j) => j.detail,
      () => "",
    );
    throw new Error(`${res.status} ${typeof detail === "string" && detail ? detail : res.statusText}`);
  }
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body: unknown) => send<T>("POST", path, body);

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
  status: (signal?: AbortSignal) => get<Status>("/status", {}, signal),
  replayEvents: (signal?: AbortSignal) =>
    get<{ today: string; events: ReplayEvent[] }>("/replay/events", {}, signal),
  subgroups: (q: { location: string; specimen: Specimen; as_of: string }, signal?: AbortSignal) =>
    get<Subgroups>("/subgroups", { ...q }, signal),
  trendFindings: (as_of: string, signal?: AbortSignal) =>
    get<TrendFindings>("/trends/findings", { as_of }, signal),
  trendSeries: (
    q: { location: string; specimen: Specimen; organism: string; antibiotic: string; as_of: string },
    signal?: AbortSignal,
  ) => get<TrendSeries>("/trends/series", { ...q }, signal),
  overview: (q: OverviewQuery, signal?: AbortSignal) => get<Overview>("/overview", { ...q }, signal),
  ingestHeldBack: (days: number) => post<IngestEntry>(`/ingest/held-back?days=${days}`, {}),
  therapy: (q: TherapyQuery, signal?: AbortSignal) => get<Therapy>("/therapy", { ...q }, signal),
  carriers: (q: { as_of: string; location?: string; phenotype?: string; days?: number; limit?: number }, signal?: AbortSignal) =>
    get<Carriers>("/carriers", { ...q }, signal),
  patient: (id: string, as_of: string, signal?: AbortSignal) =>
    get<Patient>(`/patients/${encodeURIComponent(id)}`, { as_of }, signal),
  spread: (
    q: { phenotype: string; organism?: string; profile?: string; days: number; as_of: string },
    signal?: AbortSignal,
  ) => get<Spread>("/spread", { ...q }, signal),
  cdsServices: () => get<{ services: CdsService[] }>("/cds-services"),
  cds: (service: string, body: unknown, as_of: string) =>
    send<{ cards: CdsCard[] }>("POST", `/cds-services/${service}?as_of=${as_of}`, body),
  subscriptions: (signal?: AbortSignal) => get<{ subscriptions: Subscription[] }>("/subscriptions", {}, signal),
  saveSubscription: (s: Subscription) => send<Subscription>("PUT", `/subscriptions/${encodeURIComponent(s.id)}`, s),
  deleteSubscription: (id: string) => send<{ deleted: string }>("DELETE", `/subscriptions/${encodeURIComponent(id)}`),
  resetSubscriptions: () => post<{ subscriptions: Subscription[] }>("/subscriptions/reset", {}),
  testSubscription: (id: string) => post<{ queued: Message }>(`/subscriptions/${encodeURIComponent(id)}/test`, {}),
  notifications: (q: { as_of: string; days: number; subscription?: string }, signal?: AbortSignal) =>
    get<{ as_of: string; start: string; messages: Message[] }>("/notifications", { ...q }, signal),
  deliveries: (signal?: AbortSignal) => get<{ deliveries: Delivery[] }>("/notifications/deliveries", {}, signal),
  digest: (q: { as_of: string; period: "week" | "month" }, signal?: AbortSignal) =>
    get<Digest>("/digest", { ...q }, signal),
  mockInbox: (signal?: AbortSignal) =>
    get<{ messages: { received: string; payload: Record<string, any> }[] }>("/mock-ehr/inbox", {}, signal),
  clearMockInbox: () => send<{ cleared: boolean }>("DELETE", "/mock-ehr/inbox"),
};
