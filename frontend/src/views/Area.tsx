import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import {
  api,
  type Anomalies,
  type AnomalyAlert,
  type AnomalyTotals,
  type InstitutionAnomalies,
  type Severity,
  type WardAnomalies,
} from "../api/client";
import { AvoidList } from "../components/AvoidList";
import { SeverityPill } from "../components/AlertBits";
import { daysAgo, fmtDate } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";

const SEV_RANK: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
const ease = [0.22, 1, 0.36, 1] as const;

/**
 * Exceptions-first drill-down (UX-01–03): Varha → institution → ward. Each level shows only the
 * children with something going on, as counts; the calm ones collapse into one line. No level
 * above the ward gets an overall resistance percentage.
 */
export function Area({ id }: { id?: string }) {
  const { asOf, meta, alertsVersion } = useApp();
  const { data, error, loading } = useFetch(
    (signal) => api.anomalies(asOf, signal),
    [asOf, alertsVersion, meta.data_version],
  );
  if (error) return <p className="error">Could not load the overview: {error}</p>;
  if (!data) return <p className="muted">Loading…</p>;

  const inst = data.institutions.find((i) => i.key === id && i.kind === "hospital");
  const ward = id ? data.wards[id] : undefined;
  const parent = ward ? data.institutions.find((i) => i.wards.includes(ward.ward_code)) : undefined;
  const level = ward ? "ward" : inst ? "institution" : "varha";
  const key = ward?.ward_code ?? inst?.key ?? "varha";

  return (
    <AreaLevels
      data={data}
      level={level}
      levelKey={key}
      inst={inst ?? (parent?.kind === "hospital" ? parent : undefined)}
      parent={parent}
      ward={ward}
      loading={loading}
    />
  );
}

const DEPTH = { varha: 0, institution: 1, ward: 2 } as const;
type Level = keyof typeof DEPTH;

/** Going deeper zooms in, going up zooms out, so the change of level is felt, not just read. */
const zoom = {
  enter: (dir: number) => ({ opacity: 0, scale: dir > 0 ? 0.97 : 1.03, y: dir > 0 ? 14 : -14 }),
  center: { opacity: 1, scale: 1, y: 0 },
  exit: (dir: number) => ({ opacity: 0, scale: dir > 0 ? 1.02 : 0.98 }),
};

function AreaLevels({
  data,
  level,
  levelKey,
  inst,
  parent,
  ward,
  loading,
}: {
  data: Anomalies;
  level: Level;
  levelKey: string;
  inst?: InstitutionAnomalies;
  parent?: InstitutionAnomalies;
  ward?: WardAnomalies;
  loading: boolean;
}) {
  const shown = useRef(DEPTH[level]);
  const dir = Math.sign(DEPTH[level] - shown.current) || 1;
  useEffect(() => {
    shown.current = DEPTH[level];
  }, [level]);

  return (
    <LayoutGroup>
      <div className={`area area-${level} ${loading ? "is-loading" : ""}`}>
        <LevelStepper data={data} level={level} inst={inst} parent={parent} ward={ward} />
        <AnimatePresence mode="popLayout" initial={false} custom={dir}>
          <motion.div
            key={levelKey}
            custom={dir}
            variants={zoom}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.3, ease }}
          >
            {level === "varha" && <VarhaLevel data={data} />}
            {level === "institution" && inst && <InstitutionLevel data={data} inst={inst} />}
            {level === "ward" && ward && <WardLevel ward={ward} kind={parent?.kind ?? "hospital"} />}
          </motion.div>
        </AnimatePresence>
        <p className="muted small area-def">{data.definition}</p>
      </div>
    </LayoutGroup>
  );
}

/**
 * Where you are in Varha → institution → ward, always visible (sticky). The current level is
 * filled; levels above are links; the next level says what to pick.
 */
function LevelStepper({
  data,
  level,
  inst,
  parent,
  ward,
}: {
  data: Anomalies;
  level: Level;
  inst?: InstitutionAnomalies;
  parent?: InstitutionAnomalies;
  ward?: WardAnomalies;
}) {
  const healthCentre = parent?.kind === "health_centre";
  const steps: { level: Level; kind: string; name: string; to?: string }[] = [
    { level: "varha", kind: "County", name: data.varha.label, to: href({ view: "area" }) },
    healthCentre
      ? { level: "ward", kind: "Health centre", name: ward!.label }
      : {
          level: "institution",
          kind: "Hospital",
          name: inst?.label ?? "Pick a hospital or health centre",
          to: inst && href({ view: "area", id: inst.key }),
        },
    ...(healthCentre
      ? []
      : [{ level: "ward" as const, kind: "Ward", name: ward ? `${ward.ward_code} · ${ward.label}` : "Pick a ward" }]),
  ];
  const here = steps.findIndex((s) => s.level === level);
  const up = here > 0 ? steps[here - 1] : null;

  return (
    <nav className="stepper" aria-label="Level">
      {up && (
        <a className="stepper-up" href={up.to} title={`Up to ${up.name}`}>
          <span aria-hidden>↑</span> {up.name}
        </a>
      )}
      <ol className="stepper-steps">
        {steps.map((s, i) => {
          const state = i < here ? "done" : i === here ? "current" : "next";
          const body = (
            <>
              {state === "current" && (
                <motion.span layoutId="stepper-current" className="stepper-fill" transition={{ duration: 0.3, ease }} />
              )}
              <span className="stepper-kind">{s.kind}</span>
              <span className="stepper-name">{s.name}</span>
            </>
          );
          return (
            <li key={s.level} className={`stepper-step is-${state}`} aria-current={state === "current" ? "location" : undefined}>
              {state === "done" && s.to ? <a href={s.to}>{body}</a> : <span>{body}</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function LevelHead({
  layoutId,
  eyebrow,
  title,
  sub,
  totals,
}: {
  layoutId: string;
  eyebrow: string;
  title: string;
  sub?: string;
  totals: Pick<AnomalyTotals, "anomalies" | "new" | "by_severity" | "worst" | "feed_problems">;
}) {
  return (
    <motion.section layoutId={layoutId} className={`level-head stripe-${totals.worst ?? "calm"}`}>
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {sub && <p className="ward-sub">{sub}</p>}
      </div>
      <Count totals={totals} big />
    </motion.section>
  );
}

function Count({
  totals,
  big = false,
}: {
  totals: Pick<AnomalyTotals, "anomalies" | "new" | "by_severity" | "worst" | "feed_problems">;
  big?: boolean;
}) {
  if (totals.anomalies === 0) return <div className={`count is-calm ${big ? "big" : ""}`}>Calm</div>;
  const sev = Object.entries(totals.by_severity) as [Severity, number][];
  return (
    <div className={`count ${big ? "big" : ""}`}>
      <span className={`count-n sev-text-${totals.worst}`}>{totals.anomalies}</span>
      <span className="count-label">
        anomal{totals.anomalies === 1 ? "y" : "ies"}
        <span className="count-detail">
          {sev.map(([s, n]) => `${n} ${s}`).join(" · ")}
          {totals.feed_problems ? `${sev.length ? " · " : ""}${totals.feed_problems} feed` : ""}
          {totals.new ? ` · ${totals.new} new` : ""}
        </span>
      </span>
    </div>
  );
}

function byUrgency<T extends { worst: Severity | null; anomalies: number }>(a: T, b: T) {
  return SEV_RANK[a.worst ?? "info"] - SEV_RANK[b.worst ?? "info"] || b.anomalies - a.anomalies;
}

function VarhaLevel({ data }: { data: Anomalies }) {
  const busy = data.institutions.filter((i) => i.anomalies > 0).sort(byUrgency);
  const calm = data.institutions.filter((i) => i.anomalies === 0);
  return (
    <>
      <LevelHead
        layoutId="area-varha"
        eyebrow="Wellbeing services county"
        title={data.varha.label}
        sub={`${data.varha.full} · as of ${fmtDate(data.as_of)}`}
        totals={data.varha}
      />
      {busy.length > 0 && (
        <div className="tiles">
          {busy.map((i, n) => (
            <Tile
              key={i.key}
              layoutId={`area-${i.kind === "hospital" ? i.key : i.wards[0]}`}
              to={href({ view: "area", id: i.kind === "hospital" ? i.key : i.wards[0] })}
              title={i.label}
              sub={i.full}
              totals={i}
              index={n}
            >
              {i.kind === "hospital" ? (
                <WardChips wards={i.wards.map((c) => data.wards[c]).filter((w) => w.anomalies > 0)} />
              ) : (
                <AlertLines alerts={data.wards[i.wards[0]].alerts} />
              )}
              {i.kind === "hospital" && <p className="tile-foot">{i.calm.length} of {i.wards.length} wards calm</p>}
            </Tile>
          ))}
        </div>
      )}
      <CalmLine
        items={calm.map((i) => ({ label: i.label, to: href({ view: "area", id: i.kind === "hospital" ? i.key : i.wards[0] }) }))}
        all={busy.length === 0}
        noun="institution"
      />
      <div className="placeholders">
        {data.placeholders.map((p) => (
          <div key={p} className="placeholder-tile" title="Part of Varha, but not in the demo data">
            <strong>{p}</strong>
            <span>not in demo data</span>
          </div>
        ))}
      </div>
    </>
  );
}

function InstitutionLevel({ data, inst }: { data: Anomalies; inst: InstitutionAnomalies }) {
  const wards = inst.wards.map((c) => data.wards[c]);
  const busy = wards.filter((w) => w.anomalies > 0).sort(byUrgency);
  const calm = wards.filter((w) => w.anomalies === 0);
  return (
    <>
      <LevelHead
        layoutId={`area-${inst.key}`}
        eyebrow="Hospital"
        title={inst.label}
        sub={`${inst.full} · ${inst.wards.length} wards · as of ${fmtDate(data.as_of)}`}
        totals={inst}
      />
      {busy.length > 0 && (
        <div className="tiles">
          {busy.map((w, n) => (
            <Tile
              key={w.ward_code}
              layoutId={`area-${w.ward_code}`}
              to={href({ view: "area", id: w.ward_code })}
              title={w.ward_code}
              sub={w.label}
              totals={{ ...w, by_severity: sevCounts(w.alerts), feed_problems: w.feed ? 1 : 0 }}
              index={n}
            >
              <AlertLines alerts={w.alerts} feed={w.feed} />
            </Tile>
          ))}
        </div>
      )}
      <CalmLine
        items={calm.map((w) => ({ label: w.ward_code, title: w.label, to: href({ view: "area", id: w.ward_code }) }))}
        all={busy.length === 0}
        noun="ward"
      />
      <p className="muted small area-links">
        Also: <a href={href({ view: "heatmap" })}>ward × time heatmap</a> ·{" "}
        <a href={href({ view: "spread" })}>spread across wards</a> · <a href={href({ view: "alerts" })}>all alerts</a>
      </p>
    </>
  );
}

function WardLevel({ ward, kind }: { ward: WardAnomalies; kind: "hospital" | "health_centre" }) {
  const { meta } = useApp();
  const [infection, setInfection] = useState<"uti" | "bloodstream" | "wound">("uti");
  const [showAvoid, setShowAvoid] = useState(false);
  const action = (a: AnomalyAlert) => meta.alert_types.find((t) => t.key === a.type)?.action;
  return (
    <>
      <LevelHead
        layoutId={`area-${ward.ward_code}`}
        eyebrow={kind === "hospital" ? `Ward · ${ward.ward_code}` : "Health centre"}
        title={ward.label}
        totals={{ ...ward, by_severity: sevCounts(ward.alerts), feed_problems: ward.feed ? 1 : 0 }}
      />
      {ward.anomalies === 0 ? (
        <p className="calm-note">Nothing unusual here: no active alerts and the lab feed is current.</p>
      ) : (
        <ul className="anomaly-list">
          {ward.feed && (
            <li className="anomaly sev-line-medium">
              <SeverityPill severity="medium" />
              <div>
                <strong>
                  {ward.feed.status === "gap" ? "Fewer samples than expected" : `Lab data ${ward.feed.status === "stale" ? "missing" : "delayed"}`}
                </strong>
                <p>
                  Last sample {daysAgo(ward.feed.days_since_last)}
                  {ward.feed.alert && (
                    <>
                      {" "}
                      · <a href={href({ view: "alert", id: ward.feed.alert.id })}>data-gap alert</a>
                    </>
                  )}
                </p>
              </div>
            </li>
          )}
          {ward.alerts.map((a, i) => (
            <motion.li
              key={a.id}
              className={`anomaly sev-line-${a.severity}`}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.05 * i, duration: 0.2 }}
            >
              <SeverityPill severity={a.severity} />
              <div>
                <a href={href({ view: "alert", id: a.id })}>
                  <strong>{a.type_label}</strong>
                  {a.wards.length > 1 && <span className="muted"> · {a.wards.join(", ")}</span>}
                </a>
                <p>{a.title}</p>
                <p className="muted small">
                  Since {fmtDate(a.first_seen)} · {a.triage === "new" ? "not yet triaged" : a.triage}
                  {action(a) ? ` · ${action(a)}` : ""}
                </p>
              </div>
            </motion.li>
          ))}
        </ul>
      )}

      <section className="card pad background-card">
        <h2>Background (not anomalies)</h2>
        <p className="small">
          {ward.carriers
            ? `${ward.carriers} known carrier${ward.carriers > 1 ? "s" : ""} sampled here recently. `
            : "No known carriers sampled here recently. "}
          <a href={href({ view: "ward", id: ward.ward_code })}>Open the full antibiogram →</a>
        </p>
        {!showAvoid ? (
          <button type="button" className="link-btn" onClick={() => setShowAvoid(true)}>
            Show long-standing high resistance (the ward's avoid list)
          </button>
        ) : (
          <>
            <div className="segmented small-seg">
              {meta.infections.map((i) => (
                <button
                  key={i.key}
                  type="button"
                  className={infection === i.key ? "on" : ""}
                  onClick={() => setInfection(i.key)}
                >
                  {i.label}
                </button>
              ))}
            </div>
            <AvoidList location={ward.ward_code} infection={infection} compact />
          </>
        )}
      </section>
    </>
  );
}

function Tile({
  layoutId,
  to,
  title,
  sub,
  totals,
  index,
  children,
}: {
  layoutId: string;
  to: string;
  title: string;
  sub: string;
  totals: Pick<AnomalyTotals, "anomalies" | "new" | "by_severity" | "worst" | "feed_problems">;
  index: number;
  children: React.ReactNode;
}) {
  return (
    <motion.a
      layoutId={layoutId}
      href={to}
      className={`tile stripe-${totals.worst ?? "calm"}`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.04 * index, duration: 0.25, ease }}
      whileHover={{ y: -2 }}
    >
      <div className="tile-head">
        <div>
          <strong className="tile-title">{title}</strong>
          <span className="tile-sub">{sub}</span>
        </div>
        <Count totals={totals} />
      </div>
      {children}
    </motion.a>
  );
}

function WardChips({ wards }: { wards: WardAnomalies[] }) {
  return (
    <ul className="ward-chips">
      {[...wards].sort(byUrgency).map((w) => (
        <li key={w.ward_code} className={`ward-chip sev-chip-${w.worst}`} title={w.label}>
          <span className="mono">{w.ward_code}</span> {w.anomalies}
        </li>
      ))}
    </ul>
  );
}

function AlertLines({ alerts, feed }: { alerts: AnomalyAlert[]; feed?: WardAnomalies["feed"] }) {
  const shown = alerts.slice(0, 3);
  return (
    <ul className="alert-lines">
      {feed && (
        <li>
          <span className="dot sev-dot-medium" /> Lab data {feed.status === "gap" ? "low" : feed.status}
          <span className="muted"> · last sample {daysAgo(feed.days_since_last)}</span>
        </li>
      )}
      {shown.map((a) => (
        <li key={a.id}>
          <span className={`dot sev-dot-${a.severity}`} /> {a.type_label}
          <span className="muted"> · since {fmtDate(a.first_seen)}</span>
        </li>
      ))}
      {alerts.length > shown.length && <li className="muted">+ {alerts.length - shown.length} more</li>}
    </ul>
  );
}

function CalmLine({ items, all, noun }: { items: { label: string; to: string; title?: string }[]; all: boolean; noun: string }) {
  if (items.length === 0) return null;
  return (
    <p className="calm-line">
      <span className="calm-dot" aria-hidden />
      {all ? `All ${items.length} ${noun}s calm: ` : `${items.length} ${noun}${items.length > 1 ? "s" : ""} calm: `}
      {items.map((c, i) => (
        <span key={c.to}>
          {i > 0 && ", "}
          <a href={c.to} title={c.title}>
            {c.label}
          </a>
        </span>
      ))}
    </p>
  );
}

function sevCounts(alerts: AnomalyAlert[]): Partial<Record<Severity, number>> {
  const out: Partial<Record<Severity, number>> = {};
  for (const a of [...alerts].sort((x, y) => SEV_RANK[x.severity] - SEV_RANK[y.severity])) {
    out[a.severity] = (out[a.severity] ?? 0) + 1;
  }
  return out;
}
