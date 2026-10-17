import { api, type Specimen, type SplitBy } from "../api/client";
import { fmtDate, pct } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { useApp } from "../state/AppContext";
import { fmtP } from "./AlertBits";

/**
 * Automatic subgroup-difference discovery (STAT-09): where resistance differs notably between
 * patient groups in this scope, FDR-controlled. Optionally offers to split the table by it.
 */
export function SubgroupPanel({
  location,
  specimen,
  onSplit,
}: {
  location: string;
  specimen: Specimen;
  onSplit?: (organism: string, by: SplitBy) => void;
}) {
  const { meta, asOf } = useApp();
  const { data, error, loading } = useFetch(
    (signal) => api.subgroups({ location, specimen, as_of: asOf }, signal),
    [location, specimen, asOf, meta.data_version],
  );
  const splittable = new Set(meta.split_dimensions.map((d) => d.key as string));

  return (
    <section className={`card pad subgroups ${loading ? "is-loading" : ""}`}>
      <h2>
        Differences between patient groups{" "}
        {data && (
          <span className="muted small">
            last 12 months ({fmtDate(data.window.start)} – {fmtDate(data.window.end)})
          </span>
        )}
      </h2>
      {error && <p className="error">Could not check subgroups: {error}</p>}
      {data && data.findings.length === 0 && (
        <p className="muted">
          No notable differences by {data.dimensions.map((d) => d.label.toLowerCase()).join(", ")} among{" "}
          {data.compared} comparisons with enough isolates.
        </p>
      )}
      {data && data.findings.length > 0 && (
        <ul className="subgroup-list">
          {data.findings.map((f) => (
            <li key={`${f.dimension}-${f.organism}-${f.antibiotic_code}`}>
              <p>
                <strong>{f.text}</strong>
              </p>
              <p className="muted small">
                {f.levels.map((l) => `${l.label} ${pct(l.pct)} (${l.r}/${l.n})`).join(" · ")} · q {fmtP(f.q_value)}
              </p>
              {onSplit && splittable.has(f.dimension) && (
                <button type="button" className="link-btn" onClick={() => onSplit(f.organism, f.dimension as SplitBy)}>
                  Split {f.organism} by {f.dimension_label.toLowerCase()} in the table
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {data && (
        <p className="muted small method">
          Checked automatically: resistance compared across each patient group (Fisher / chi-square test) for every
          organism and antibiotic with at least 30 first isolates per group; {data.compared} comparisons,
          false-discovery rate 5 %.
        </p>
      )}
    </section>
  );
}
