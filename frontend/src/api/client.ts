// Thin client for the backend API (API-01). Vite proxies /api to the FastAPI server in dev.

export interface Health {
  status: string;
  cultures: number;
  data_start: string;
  data_end: string;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<Health>("/health"),
};
