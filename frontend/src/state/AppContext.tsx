import { createContext, useContext } from "react";
import type { Meta } from "../api/client";

export interface AppState {
  meta: Meta;
  /** Global time cursor (LIVE-01): every view computes as if this day were today. */
  asOf: string;
  setAsOf: (date: string) => void;
}

export const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside AppContext");
  return ctx;
}
