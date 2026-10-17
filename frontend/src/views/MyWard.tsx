import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { api, type Specimen } from "../api/client";
import { AlertStrip } from "../components/AlertStrip";
import { Antibiogram } from "../components/Antibiogram";
import { CellDetail } from "../components/CellDetail";
import { FilterBar, type Filters } from "../components/FilterBar";
import { FreshnessBadge } from "../components/FreshnessBadge";
import { Legend } from "../components/Legend";
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
  const [selected, setSelected] = useState<{ organism: string; code: string } | null>(null);

  const ab = useFetch(
    (signal) => api.antibiogram({ location, specimen, ...filters, as_of: asOf }, signal),
    [location, specimen, filters.sex, filters.age_band, filters.hospital_acquired, asOf],
  );
  const fresh = useFetch((signal) => api.freshness(asOf, signal), [asOf]);
  const data = ab.data;
  const row = selected && data?.organisms.find((o) => o.organism === selected.organism);
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
          <Antibiogram data={data} onSelect={(organism, code) => setSelected({ organism, code })} />
        </motion.div>
      )}
      <Legend />

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
