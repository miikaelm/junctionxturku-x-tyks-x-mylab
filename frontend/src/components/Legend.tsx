import { useApp } from "../state/AppContext";

export function Legend() {
  const { meta } = useApp();
  const { good_below, warn_below, min_isolates } = meta.thresholds;
  return (
    <div className="legend">
      <span className="legend-item">
        <span className="swatch tier-good" /> &lt; {good_below} % resistant (no colour: nothing to act on)
      </span>
      <span className="legend-item">
        <span className="swatch tier-warn" /> {good_below}–{warn_below} %
      </span>
      <span className="legend-item">
        <span className="swatch tier-bad" /> ≥ {warn_below} %
      </span>
      <span className="legend-item">
        <span className="swatch tier-none" /> fewer than {min_isolates} isolates: counts shown (R / tested)
      </span>
      <span className="legend-item">
        <span className="swatch swatch-intrinsic" /> intrinsic resistance
      </span>
      <span className="legend-item">
        <sup className="ab-mark">H</sup>
        <sup className="ab-mark">P</sup>
        <sup className="ab-mark">A</sup> too few on this ward, showing all hospital wards / all health
        centres / all locations
      </span>
      <span className="legend-item">
        <span className="ci ci-compact legend-ci">
          <span className="ci-range" style={{ left: "20%", width: "40%" }} />
          <span className="ci-point" style={{ left: "35%" }} />
        </span>
        95 % confidence interval
      </span>
    </div>
  );
}
