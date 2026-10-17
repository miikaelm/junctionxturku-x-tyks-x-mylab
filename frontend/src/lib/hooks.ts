import { useEffect, useState, useSyncExternalStore } from "react";

// Requests in flight across all useFetch calls, so replay can wait until every open view has
// caught up before stepping on (LIVE-02).
let inflight = 0;
const listeners = new Set<() => void>();
function track(delta: number) {
  inflight += delta;
  listeners.forEach((l) => l());
}

/** True while no useFetch request is loading. */
export function useIdle(): boolean {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => inflight === 0,
  );
}

/** State persisted in localStorage (per-viewer conveniences like the remembered ward). */
export function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // storage unavailable (private mode): keep working in memory
    }
  }, [key, value]);
  return [value, setValue] as const;
}

/**
 * Fetch whenever `deps` change; aborts stale requests and keeps the previous data while the
 * next one loads, so scrubbing the time cursor doesn't flash empty states.
 */
export function useFetch<T>(load: (signal: AbortSignal) => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    track(1);
    load(ctrl.signal)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        track(-1);
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, loading };
}
