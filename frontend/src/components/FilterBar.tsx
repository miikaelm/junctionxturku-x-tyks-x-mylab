import type { InfectionFocus } from "./WardExceptions";
import { useApp } from "../state/AppContext";

export interface Filters {
  sex?: "F" | "M";
  age_band?: string;
  hospital_acquired?: boolean;
}

interface Props {
  focus: InfectionFocus;
  onFocus: (f: InfectionFocus) => void;
  filters: Filters;
  onFilters: (f: Filters) => void;
}

const SHORT: Record<InfectionFocus, string> = {
  all: "All",
  uti: "Urinary",
  bloodstream: "Bloodstream",
  wound: "Wound",
};

export function Segmented<T extends string>(props: {
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

/**
 * What narrows the picture (VIEW-02, UX-09): the infection in focus and the patient group. The ward
 * is not a filter: it is chosen in the page title, since changing it moves to another place.
 */
export function FilterBar({ focus, onFocus, filters, onFilters }: Props) {
  const { meta } = useApp();
  const acquisition =
    filters.hospital_acquired === undefined ? "any" : filters.hospital_acquired ? "hospital" : "community";
  const activeCount = [filters.sex, filters.age_band, filters.hospital_acquired].filter((v) => v !== undefined).length;

  return (
    <div className="filters">
      <div className="filters-main">
        <div className="field">
          <span className="field-label">Infection</span>
          <Segmented
            label="Infection"
            value={focus}
            onChange={onFocus}
            options={(["all", ...meta.infections.map((i) => i.key)] as InfectionFocus[]).map((k) => ({
              value: k,
              label: SHORT[k],
            }))}
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
