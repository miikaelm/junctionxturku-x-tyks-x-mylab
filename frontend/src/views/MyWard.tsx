import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { api, type OrganismRow, type Specimen, type SplitBy } from "../api/client";
import { AlertStrip } from "../components/AlertStrip";
import { Antibiogram } from "../components/Antibiogram";
import { CellDetail } from "../components/CellDetail";
import { FilterBar, type Filters } from "../components/FilterBar";
import { FreshnessBadge } from "../components/FreshnessBadge";
import { Legend } from "../components/Legend";
import { SubgroupPanel } from "../components/SubgroupPanel";
import { fmtDate } from "../lib/format";
import { useFetch, useLocalStorage } from "../lib/hooks";
import { useApp } from "../state/AppContext";

const SPECIMEN_LABEL: Record<Specimen, string> = {
  urine: "Urine",
  blood: "Blood",
  wound: "Wound",
};

/** V1 My Ward: the clinician's landing page (VIEW-01). */
export function MyWard() {
  const { meta, asOf } = useApp();
  const knownLocations = new Set([...meta.wards.map((w) => w.ward_code), ...meta.locations.map((l) => l.code)]);
  const [storedLocation, setLocation] = useLocalStorage("aei.location", meta.wards[0].ward_code);
  const location = knownLocations.has(storedLocation) ? storedLocation : meta.wards[0].ward_code;
  const [specimen, setSpecimen] = useLocalStorage<Specimen>("aei.specimen", "urine");
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
          <p className="eyebrow">My ward</p>
          <h1>{data?.scope.label ?? "…"}</h1>
          <p className="ward-sub">
            {SPECIMEN_LABEL[specimen]} cultures · resistance among first isolates · as of{" "}
            {fmtDate(asOf)}
          </p>
        </div>
        <FreshnessBadge freshness={fresh.data} location={location} />
      </section>

      <AlertStrip location={location} />

      <FilterBar
        location={location}
        onLocation={setLocation}
        specimen={specimen}
        onSpecimen={setSpecimen}
        filters={filters}
        onFilters={setFilters}
      />

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
