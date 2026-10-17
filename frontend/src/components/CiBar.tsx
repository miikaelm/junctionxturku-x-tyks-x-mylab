import type { Estimate } from "../api/client";
import { useApp } from "../state/AppContext";

/**
 * 95 % confidence interval on a 0–100 % track (STAT-02). A wide bar = an uncertain number.
 * The full-size version marks the traffic-light thresholds.
 */
export function CiBar({ est, compact = false }: { est: Estimate; compact?: boolean }) {
  const { meta } = useApp();
  const { good_below, warn_below } = meta.thresholds;
  return (
    <span className={`ci ${compact ? "ci-compact" : ""} ${est.sufficient ? "" : "ci-weak"}`} aria-hidden>
      {!compact && (
        <>
          <span className="ci-tick" style={{ left: `${good_below}%` }} />
          <span className="ci-tick ci-tick-strong" style={{ left: `${warn_below}%` }} />
        </>
      )}
      <span className="ci-range" style={{ left: `${est.ci_low}%`, width: `${Math.max(est.ci_high - est.ci_low, 0.8)}%` }} />
      {est.pct !== null && <span className="ci-point" style={{ left: `${est.pct}%` }} />}
    </span>
  );
}
