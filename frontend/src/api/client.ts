import type { TimelineEntry, DailySummary } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export interface DayDataResponse {
  entries: TimelineEntry[];
  summary: DailySummary;
}

export async function fetchDayData(day: string): Promise<DayDataResponse> {
  const res = await fetch(`${API_BASE_URL}/api/day/${day}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch day data. Server returned ${res.status}`);
  }
  return res.json();
}