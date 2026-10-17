import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { api, type OrganismRow, type Specimen, type SplitBy } from "../api/client";
import { Antibiogram } from "../components/Antibiogram";
import { CellDetail } from "../components/CellDetail";
import { FilterBar, Segmented, type Filters } from "../components/FilterBar";
import { FreshnessBadge } from "../components/FreshnessBadge";
import { Legend } from "../components/Legend";
import { SubgroupPanel } from "../components/SubgroupPanel";
import { TherapyHelper } from "../components/TherapyHelper";
import { WardExceptions, type InfectionFocus } from "../components/WardExceptions";
import { fmtDate } from "../lib/format";
import { useFetch, useLocalStorage } from "../lib/hooks";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";

const SPECIMEN_LABEL: Record<Specimen, string> = {
  urine: "Urine",
  blood: "Blood",
  wound: "Wound",
};

/**
 * V1 My Ward: the clinician's landing page (VIEW-01). Exceptions first (UX-05): what not to use
 * and what is going on here; the ranked coverage and the full antibiogram follow below. The ward
 * is the place (UX-09): chosen in the title, it is part of the address (#/ward/URO).
 */
export function MyWard({ ward }: { ward?: string }) {
  const { meta, asOf, role } = useApp();
  const known = new Set([...meta.wards.map((w) => w.ward_code), ...meta.locations.map((l) => l.code)]);
  const [stored, setStored] = useLocalStorage("aei.location", meta.wards[0].ward_code);
  const own = role.role === "clinician" && role.ward && known.has(role.ward) ? role.ward : null;
  const location = ward && known.has(ward) ? ward : (own ?? (known.has(stored) ? stored : meta.wards[0].ward_code));
  useEffect(() => {
    if (location !== stored) setStored(location);
  }, [location]); // eslint-disable-line react-hooks/exhaustive-deps
  const goTo = (code: string) => {
    window.location.hash = href({ view: "ward", id: code });
  };
  // Infections side by side unless one is in focus (UX-08); the detail table is one specimen.
  const [focus, setFocus] = useLocalStorage<InfectionFocus>("aei.infection", "all");
  const [tableSpecimen, setTableSpecimen] = useLocalStorage<Specimen>("aei.specimen", "urine");
  const specimen = focus === "all" ? tableSpecimen : (meta.infections.find((i) => i.key === focus)?.specimen ?? "urine");
  const [filters, setFilters] = useState<Filters>({});
  const [selected, setSelected] = useState<{ organism: string; code: string; sub?: string } | null>(null);
  // Row split (STAT-07): null = the default for this specimen, "none" = no split.
  const [splitChoice, setSplitChoice] = useState<{ specimen: Specimen; by: SplitBy | "none"; organism?: string } | null>(
    null,
  );
  const split = splitChoice?.specimen === specimen ? splitChoice : null;

  const ab = useFetch(
    (signal) =>
      api.antibiogram(
        { location, specimen, ...filters, split_by: split?.by, split_organism: split?.organism, as_of: asOf },
        signal,
      ),
    [location, specimen, filters.sex, filters.age_band, filters.hospital_acquired, split?.by, split?.organism, asOf, meta.data_version],
  );
  const fresh = useFetch((signal) => api.freshness(asOf, signal), [asOf, meta.data_version]);
  const data = ab.data;
  const row = selected && subRow(data?.organisms.find((o) => o.organism === selected.organism), selected.sub);
  const splitRow = data?.organisms.find((o) => o.split);
  const splitLabel = (by: string) => meta.split_dimensions.find((d) => d.key === by)?.label.toLowerCase() ?? by;
  const cell = row && selected ? row.cells[selected.code] : null;
  const antibiotic = selected && data?.antibiotics.find((a) => a.code === selected.code);

  return (
    <>
      <section className="ward-head">
        <div>
          <p className="eyebrow">
            {own === location ? <span className="mine-badge">My ward</span> : own ? "Viewing another ward" : "Ward"}
          </p>
          <WardSwitcher location={location} onChange={goTo} />
          <p className="ward-sub">
            {own && own !== location && (
              <>
                <a href={href({ view: "ward", id: own })}>← Back to my ward ({own})</a> ·{" "}
              </>
            )}
            as of {fmtDate(asOf)}
          </p>
        </div>
        <FreshnessBadge freshness={fresh.data} location={location} />
      </section>

      <FilterBar focus={focus} onFocus={setFocus} filters={filters} onFilters={setFilters} />

      <WardExceptions location={location} focus={focus} filters={filters} freshness={fresh.data} />

      <div className="detail-head">
        <h2 className="section-title detail-title">More detail</h2>
        {focus === "all" ? (
          <div className="field">
            <span className="field-label">Tables for</span>
            <Segmented
              label="Specimen"
              value={specimen}
              onChange={setTableSpecimen}
              options={(Object.keys(SPECIMEN_LABEL) as Specimen[]).map((k) => ({ value: k, label: SPECIMEN_LABEL[k] }))}
            />
          </div>
        ) : (
          <span className="muted small">{SPECIMEN_LABEL[specimen]} cultures</span>
        )}
      </div>
      <TherapyHelper location={location} specimen={specimen} filters={filters} />

      {ab.error && <p className="error">Could not load the antibiogram: {ab.error}</p>}
      {data && (
        <motion.div
          className={`ab-card ${ab.loading ? "is-loading" : ""}`}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <Antibiogram data={data} onSelect={(organism, code, sub) => setSelected({ organism, code, sub })} />
        </motion.div>
      )}
      {splitRow?.split && (
        <p className="split-note muted small">
          {splitRow.organism} is split by {splitLabel(splitRow.split.by)}
          {splitRow.split.default ? " by default: a clinically known difference" : ""}.{" "}
          <button type="button" className="link-btn" onClick={() => setSplitChoice({ specimen, by: "none" })}>
            Remove split
          </button>
        </p>
      )}
      {split?.by === "none" && (
        <p className="split-note muted small">
          <button type="button" className="link-btn" onClick={() => setSplitChoice(null)}>
            Restore the default split
          </button>
        </p>
      )}
      <Legend />
      <SubgroupPanel
        location={location}
        specimen={specimen}
        onSplit={(organism, by) => {
          setFilters((f) => ({ ...f, [by]: undefined }));
          setSplitChoice({ specimen, by, organism });
        }}
      />

      <AnimatePresence>
        {data && row && cell && antibiotic && (
          <CellDetail
            key={`${row.organism}-${antibiotic.code}`}
            data={data}
            row={row}
            cell={cell}
            antibiotic={antibiotic}
            onClose={() => setSelected(null)}
          />
        )}
      </AnimatePresence>
    </>
  );
}

/** The organism row, or one of its split sub-rows shaped like a row (for the cell drawer). */
function subRow(row: OrganismRow | undefined, sub: string | undefined): OrganismRow | undefined {
  if (!row || !sub) return row;
  const s = row.split?.rows.find((r) => r.label === sub);
  return s ? { ...row, organism: `${row.organism} · ${s.label}`, isolates: s.isolates, cells: s.cells } : undefined;
}

/** The ward as the page title (UX-09): a native select over the heading, so it works everywhere. */
function WardSwitcher({ location, onChange }: { location: string; onChange: (code: string) => void }) {
  const { meta } = useApp();
  const hospital = meta.wards.filter((w) => w.institution === "hospital");
  const primary = meta.wards.filter((w) => w.institution === "primary_care");
  const label =
    meta.wards.find((w) => w.ward_code === location)?.ward_en ?? meta.locations.find((l) => l.code === location)?.label ?? location;
  return (
    <label className="ward-switch" title="Change ward">
      <h1 aria-hidden>
        {label} <span className="ward-switch-caret">▾</span>
      </h1>
      <select value={location} onChange={(e) => onChange(e.target.value)} aria-label="Ward">
        <optgroup label="Hospital wards">
          {hospital.map((w) => (
            <option key={w.ward_code} value={w.ward_code}>
              {w.ward_en} ({w.ward_code})
            </option>
          ))}
        </optgroup>
        <optgroup label="Health centres">
          {primary.map((w) => (
            <option key={w.ward_code} value={w.ward_code}>
              {w.ward_en} ({w.ward_code})
            </option>
          ))}
        </optgroup>
        <optgroup label="Combined">
          {meta.locations.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </optgroup>
      </select>
    </label>
  );
}
