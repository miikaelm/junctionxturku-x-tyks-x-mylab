import { addDays } from "../lib/format";
import { useApp } from "../state/AppContext";

/** Global as-of control (LIVE-01, V8), shown in the demo bar. */
export function TimeCursor() {
  const { meta, asOf, setAsOf } = useApp();
  const isToday = asOf === meta.default_as_of;
  const step = (days: number) => {
    const next = addDays(asOf, days);
    if (next >= meta.data_start && next <= meta.default_as_of) setAsOf(next);
  };

  return (
    <div className={`cursor ${isToday ? "" : "replaying"}`}>
      <span className="cursor-label">{isToday ? "Today" : "Viewing as of"}</span>
      <div className="cursor-controls">
        <button type="button" onClick={() => step(-7)} title="Back one week" aria-label="Back one week">
          «
        </button>
        <button type="button" onClick={() => step(-1)} title="Back one day" aria-label="Back one day">
          ‹
        </button>
        <label className="cursor-date">
          <span className="sr-only">As-of date</span>
          <input
            type="date"
            value={asOf}
            min={meta.data_start}
            max={meta.default_as_of}
            onChange={(e) => e.target.value && setAsOf(e.target.value)}
          />
        </label>
        <button type="button" onClick={() => step(1)} title="Forward one day" aria-label="Forward one day">
          ›
        </button>
        <button type="button" onClick={() => step(7)} title="Forward one week" aria-label="Forward one week">
          »
        </button>
      </div>
      {!isToday && (
        <button type="button" className="cursor-reset" onClick={() => setAsOf(meta.default_as_of)}>
          Back to today
        </button>
      )}
    </div>
  );
}
