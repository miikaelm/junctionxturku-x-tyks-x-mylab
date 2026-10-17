import { motion } from "motion/react";
import { useEffect } from "react";
import {
  windowCell,
  type Antibiogram,
  type Antibiotic,
  type Cell,
  type Estimate,
  type NationalRef,
  type OrganismRow,
  type TimeWindow,
  type WindowCell,
} from "../api/client";
import { fmtDate, pct, tier } from "../lib/format";
import { useApp } from "../state/AppContext";
import { CiBar } from "./CiBar";

interface Props {
  data: Antibiogram;
  row: OrganismRow;
  cell: Cell;
  antibiotic: Antibiotic;
  onClose: () => void;
}

/**
 * Explains one cell: every level and window, counts, intervals, what was shown and why, and the
 * national figure for comparison (DATA-08).
 */
export function CellDetail({ data, row, cell, antibiotic, onClose }: Props) {
  const { meta } = useApp();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const [recentWin, annualWin] = data.windows;

  return (
    <>
      <motion.div
        className="drawer-backdrop"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      />
      <motion.aside
        className="drawer"
        role="dialog"
        aria-label={`${row.organism} and ${antibiotic.name}`}
        initial={{ x: 48, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 48, opacity: 0 }}
        transition={{ type: "spring", stiffness: 420, damping: 38 }}
      >
        <header className="drawer-head">
          <div>
            <p className="eyebrow">{data.scope.label} · {data.scope.specimen}</p>
            <h2>
              <em>{row.organism}</em>
              <span className="drawer-x">×</span>
              {antibiotic.name}
            </h2>
            <p className="muted small">
              {antibiotic.code} · {antibiotic.name_fi} · {antibiotic.class}
            </p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        {cell.intrinsic ? (
          <div className="callout callout-intrinsic">
            <strong>Intrinsically resistant.</strong> {row.organism} is naturally resistant to{" "}
            {antibiotic.name} (EUCAST Expected Resistant Phenotypes). This is not a surveillance
            finding and never triggers an alert: the agent should not be used for this organism.
          </div>
        ) : data.period ? (
          <p className="drawer-summary">{periodSummary(data, cell, meta.thresholds.min_isolates)}</p>
        ) : (
          <p className="drawer-summary">{summary(data, cell, meta.thresholds.min_isolates)}</p>
        )}

        {data.period ? (
          <WindowSection title={recentWin.label} win={recentWin} wc={windowCell(cell, recentWin.key)} data={data} />
        ) : (
          <>
            <WindowSection title="Last 4 weeks" win={recentWin} wc={cell.recent} data={data} />
            <WindowSection title="Last 12 months" win={annualWin} wc={cell.annual} data={data} />
          </>
        )}
        {!cell.intrinsic && <NationalSection nat={cell.national} local={localFigure(data, cell)} />}

        <footer className="drawer-foot">
          Counts use the first isolate per patient, organism and specimen in each window. A
          percentage is shown only with at least {meta.thresholds.min_isolates} isolates; bars
          show the 95 % Wilson confidence interval, with ticks at {meta.thresholds.good_below} %
          and {meta.thresholds.warn_below} %.
        </footer>
      </motion.aside>
    </>
  );
}

function WindowSection({ title, win, wc, data }: { title: string; win: TimeWindow; wc: WindowCell; data: Antibiogram }) {
  const { meta } = useApp();
  return (
    <section className="drawer-section">
      <h3>
        {title}
        <span className="muted small">
          {fmtDate(win.start)} – {fmtDate(win.end)}
        </span>
      </h3>
      <ul className="levels">
        {wc.levels.map((e, i) => (
          <li key={data.levels[i].location} className={`level tier-${tier(e, meta.thresholds)} ${wc.shown === i ? "is-shown" : ""}`}>
            <div className="level-top">
              <span className="level-label">
                {data.levels[i].label}
                {wc.shown === i && <span className="tag">shown</span>}
                {!e.sufficient && e.n > 0 && <span className="tag tag-muted">too few</span>}
              </span>
              <span className="level-val">
                {e.sufficient ? pct(e.pct) : "–"}
                <span className="muted small"> {e.r}/{e.n} R</span>
              </span>
            </div>
            {e.n > 0 ? <CiBar est={e} /> : <span className="muted small">No isolates</span>}
            {e.n > 0 && (
              <span className="level-ci muted small">
                95 % CI {Math.round(e.ci_low)}–{Math.round(e.ci_high)} %
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The figure the table shows for this cell (12 months, or the chosen period). */
function localFigure(data: Antibiogram, cell: Cell): Estimate | null {
  const key = data.period ? data.windows[0].key : "annual";
  const wc = windowCell(cell, key);
  return wc.shown === null ? null : wc.levels[wc.shown];
}

function NationalSection({ nat, local }: { nat: NationalRef | null; local: Estimate | null }) {
  return (
    <section className="drawer-section">
      <h3>
        Finland, for comparison
        <span className="muted small">reference only</span>
      </h3>
      {nat ? (
        <>
          <p className="national-line">
            <strong className="mono">{nat.pct} %</strong> resistant in {nat.year}
            {nat.group ? `, ${nat.group}` : ""} ({nat.specimen_label}, {nat.n.toLocaleString("en-GB")} first isolates
            nationwide)
            {local?.pct != null && (
              <span className="muted">
                {" "}
                · here {Math.round(local.pct)} %
                {local.ci_low > nat.pct ? ", above the national figure (whole interval)" : ""}
                {local.ci_high < nat.pct ? ", below the national figure (whole interval)" : ""}
              </span>
            )}
          </p>
          <p className="muted small">
            <a href={nat.url} target="_blank" rel="noreferrer">
              {nat.source}
            </a>{" "}
            ({nat.tables.join(", ")}). Finres also counts the first isolate per patient, but per calendar year and from
            every Finnish laboratory
            {nat.specimen_label === "pus" ? "; our wound samples are compared with its pus samples" : ""}
            {nat.pooled ? "; women and men pooled, weighted by the number tested" : ""}.
          </p>
        </>
      ) : (
        <p className="muted small">THL Finres publishes no national figure for this combination.</p>
      )}
    </section>
  );
}

function periodSummary(data: Antibiogram, cell: Cell, minN: number): string {
  const win = data.windows[0];
  const wc = windowCell(cell, win.key);
  const own = wc.levels[0];
  if (wc.shown === null) return `Too few isolates for a reliable percentage at any level in ${win.label} (${own.r}/${own.n} here).`;
  if (wc.shown === 0) return `${win.label} on ${data.levels[0].label}: ${describe(own)}.`;
  return `Only ${own.n} isolate${own.n === 1 ? "" : "s"} on ${data.levels[0].label} in ${win.label} (fewer than ${minN}), so the ${data.levels[wc.shown].label.toLowerCase()} figure is shown: ${describe(wc.levels[wc.shown])}.`;
}

function describe(e: Estimate): string {
  return `${e.r} of ${e.n} resistant (${pct(e.pct)}, 95 % CI ${Math.round(e.ci_low)}–${Math.round(e.ci_high)} %)`;
}

function summary(data: Antibiogram, cell: Cell, minN: number): string {
  const parts: string[] = [];
  const own = cell.annual.levels[0];
  const shown = cell.annual.shown;
  if (shown === null) {
    parts.push(`Too few isolates for a reliable 12-month percentage at any level (${own.r}/${own.n} on this ward).`);
  } else if (shown === 0) {
    parts.push(`Last 12 months on ${data.levels[0].label}: ${describe(own)}.`);
  } else {
    const e = cell.annual.levels[shown];
    parts.push(
      `Only ${own.n} isolate${own.n === 1 ? "" : "s"} on ${data.levels[0].label} in 12 months (fewer than ${minN}), so the ${data.levels[shown].label.toLowerCase()} figure is shown: ${describe(e)}.`,
    );
  }
  const recent = cell.recent.levels[0];
  if (recent.sufficient) parts.push(`Last 4 weeks: ${describe(recent)}.`);
  else if (recent.n > 0) parts.push(`Last 4 weeks: ${recent.r} of ${recent.n} resistant, too few for a percentage; read it as a signal only.`);
  else parts.push("No isolates in the last 4 weeks.");
  return parts.join(" ");
}
