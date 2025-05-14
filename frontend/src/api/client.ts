import type { TimelineEntry, DailySummary } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export interface DayResponse {
  entries: TimelineEntry[];
  summary: DailySummary;
}

/** Fetch /api/day/{YYYY-MM-DD} */
export async function getDay(day: string): Promise<DayResponse> {
  const res = await fetch(`${BASE_URL}/api/day/${day}`);
  if (!res.ok) throw new Error(`Server returned ${res.status}`);
  return res.json();
}
