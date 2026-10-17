import type { Specimen } from "../api/client";
import { useApp } from "../state/AppContext";

export interface Filters {
  sex?: "F" | "M";
  age_band?: string;
  hospital_acquired?: boolean;
}

interface Props {
  location: string;
  onLocation: (code: string) => void;
  specimen: Specimen;
  onSpecimen: (s: Specimen) => void;
  filters: Filters;
  onFilters: (f: Filters) => void;
}

function Segmented<T extends string>(props: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={props.label}>
      {props.options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={props.value === o.value}
          className={props.value === o.value ? "on" : ""}
          onClick={() => props.onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Ward, specimen and patient filters (VIEW-02). Ward and specimen are remembered. */
export function FilterBar({ location, onLocation, specimen, onSpecimen, filters, onFilters }: Props) {
  const { meta } = useApp();
  const hospital = meta.wards.filter((w) => w.institution === "hospital");
  const primary = meta.wards.filter((w) => w.institution === "primary_care");
  const acquisition =
    filters.hospital_acquired === undefined ? "any" : filters.hospital_acquired ? "hospital" : "community";
  const activeCount = [filters.sex, filters.age_band, filters.hospital_acquired].filter((v) => v !== undefined).length;

  return (
    <div className="filters">
      <div className="filters-main">
        <label className="field">
          <span className="field-label">Ward</span>
          <select value={location} onChange={(e) => onLocation(e.target.value)}>
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
        <div className="field">
          <span className="field-label">Specimen</span>
          <Segmented
            label="Specimen"
            value={specimen}
            onChange={onSpecimen}
            options={[
              { value: "urine", label: "Urine" },
              { value: "blood", label: "Blood" },
              { value: "wound", label: "Wound" },
            ]}
          />
        </div>
      </div>

      <div className="filters-patient">
        <div className="field">
          <span className="field-label">Sex</span>
          <Segmented
            label="Sex"
            value={filters.sex ?? "any"}
            onChange={(v) => onFilters({ ...filters, sex: v === "any" ? undefined : v })}
            options={[
              { value: "any", label: "All" },
              { value: "F", label: "Women" },
              { value: "M", label: "Men" },
            ]}
          />
        </div>
        <label className="field">
          <span className="field-label">Age</span>
          <select
            value={filters.age_band ?? ""}
            onChange={(e) => onFilters({ ...filters, age_band: e.target.value || undefined })}
          >
            <option value="">All ages</option>
            {meta.age_bands.map((b) => (
              <option key={b} value={b}>
                {b} years
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Acquired</span>
          <select
            value={acquisition}
            onChange={(e) =>
              onFilters({
                ...filters,
                hospital_acquired: e.target.value === "any" ? undefined : e.target.value === "hospital",
              })
            }
          >
            <option value="any">Any onset</option>
            <option value="hospital">Hospital-acquired (day 3+)</option>
            <option value="community">Community / early</option>
          </select>
        </label>
        {activeCount > 0 && (
          <button type="button" className="link-btn" onClick={() => onFilters({})}>
            Clear {activeCount} filter{activeCount > 1 ? "s" : ""}
          </button>
        )}
      </div>
    </div>
  );
}
