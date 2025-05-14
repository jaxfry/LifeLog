import { TimelineEntry, DailySummary } from "../types/timeline"

const BASE_URL = "http://localhost:8000/api"

export async function fetchTimeline(day: string): Promise<TimelineEntry[]> {
  const res = await fetch(`${BASE_URL}/enriched/${day}`)
  if (!res.ok) throw new Error("Failed to fetch timeline")
  return res.json()
}

export async function fetchSummary(day: string): Promise<DailySummary> {
  const res = await fetch(`${BASE_URL}/summary/${day}`)
  if (!res.ok) throw new Error("Failed to fetch summary")
  return res.json()
}
