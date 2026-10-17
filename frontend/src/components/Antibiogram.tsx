import { Fragment } from "react";
import type { Antibiogram as AntibiogramData, Cell, Estimate, Meta } from "../api/client";
import { levelMark, pct, tier } from "../lib/format";
import { useApp } from "../state/AppContext";
import { CiBar } from "./CiBar";

interface Props {
  data: AntibiogramData;
  /** `sub` is the split value's label when a sub-row cell was clicked. */
  onSelect: (organism: string, code: string, sub?: string) => void;
}

/** Organism × antibiotic table, each cell showing last 4 weeks next to last 12 months. */
export function Antibiogram({ data, onSelect }: Props) {
  return (
    <div className="ab-scroll">
      <table className="ab">
        <thead>
          <tr>
            <th className="ab-org-head" scope="col">
              <span>Organism</span>
              <span className="ab-org-head-sub">first isolates · 12 mo / 4 wk</span>
            </th>
            {data.antibiotics.map((a) => (
              <th key={a.code} scope="col" className="ab-abx-head" title={`${a.name} (${a.class})`}>
                <span className="ab-abx-code">{a.code}</span>
                <span className="ab-abx-name">{a.name.replace(" (screen)", "")}</span>
                <span className="ab-abx-windows" aria-hidden>
                  <span>4 wk</span>
                  <span>12 mo</span>
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.organisms.map((o) => {
            const ownAnnual = o.isolates.annual[0];
            const ownRecent = o.isolates.recent[0];
            return (
              <Fragment key={o.organism}>
              <tr className={ownAnnual === 0 ? "ab-row-empty" : ""}>
                <th scope="row" className="ab-org">
                  <span className="ab-org-name">{o.organism}</span>
                  <span className="ab-org-meta">
                    <span className="ab-share" aria-hidden>
                      <span style={{ width: `${Math.max(o.share_annual * 100, ownAnnual ? 2 : 0)}%` }} />
                    </span>
                    <span className="mono">
                      {ownAnnual} / {ownRecent}
                    </span>
                  </span>
                </th>
                {data.antibiotics.map((a) => {
                  const cell = o.cells[a.code];
                  return (
                    <td key={a.code} className="ab-td">
                      {cell ? (
                        <CellButton
                          cell={cell}
                          levels={data.levels}
                          label={`${o.organism}, ${a.name}`}
                          onClick={() => onSelect(o.organism, a.code)}
                        />
                      ) : (
                        <span className="ab-na" title="Not tested / not reported for this organism">
                          ·
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
              {o.split?.rows.map((sub) => (
                <tr key={String(sub.value)} className="ab-subrow">
                  <th scope="row" className="ab-org ab-sub">
                    <span className="ab-org-name">↳ {sub.label}</span>
                    <span className="ab-org-meta">
                      <span className="mono">
                        {sub.isolates.annual[0]} / {sub.isolates.recent[0]}
                      </span>
                    </span>
                  </th>
                  {data.antibiotics.map((a) => {
                    const cell = sub.cells[a.code];
                    return (
                      <td key={a.code} className="ab-td">
                        {cell ? (
                          <CellButton
                            cell={cell}
                            levels={data.levels}
                            label={`${o.organism} (${sub.label}), ${a.name}`}
                            onClick={() => onSelect(o.organism, a.code, sub.label)}
                          />
                        ) : (
                          <span className="ab-na">·</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CellButton({
  cell,
  levels,
  label,
  onClick,
}: {
  cell: Cell;
  levels: AntibiogramData["levels"];
  label: string;
  onClick: () => void;
}) {
  const { meta } = useApp();
  if (cell.intrinsic) {
    return (
      <button type="button" className="ab-cell ab-intrinsic" onClick={onClick} aria-label={`${label}: intrinsically resistant`}>
        <span>Intrinsic R</span>
      </button>
    );
  }

  const recent = cell.recent.levels[0];
  const annualIdx = cell.annual.shown;
  const annual = annualIdx === null ? cell.annual.levels[0] : cell.annual.levels[annualIdx];
  const mark = annualIdx ? levelMark(levels[annualIdx].level, levels[annualIdx].location) : "";

  return (
    <button type="button" className="ab-cell" onClick={onClick} aria-label={`${label}: details`}>
      <Half est={recent} thresholds={meta.thresholds} kind="recent" />
      <Half est={annual} thresholds={meta.thresholds} kind="annual" mark={mark} fallback={annualIdx === null} />
    </button>
  );
}

function Half({
  est,
  thresholds,
  kind,
  mark = "",
  fallback = false,
}: {
  est: Estimate;
  thresholds: Meta["thresholds"];
  kind: "recent" | "annual";
  mark?: string;
  fallback?: boolean;
}) {
  const t = tier(est, thresholds);
  let value: string;
  if (est.n === 0) value = "–";
  else if (est.sufficient && !fallback) value = pct(est.pct);
  else value = `${est.r}/${est.n}`; // too few for a percentage: show counts (STAT-03)

  return (
    <span className={`ab-half ab-${kind} tier-${t} ${mark ? "is-fallback" : ""}`}>
      <span className="ab-val">
        {value}
        {mark && <sup className="ab-mark">{mark}</sup>}
      </span>
      {est.n > 0 && <CiBar est={est} compact />}
    </span>
  );
}
