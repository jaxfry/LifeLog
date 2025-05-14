import { useEffect, useState } from "react";
import { TimelineEntry, DailySummary } from "../types";
import SummaryPanel from "../components/SummaryPanel";
import Timeline from "../components/Timeline";

export default function DayView() {
  const [summary, setSummary] = useState<DailySummary | null>(null);
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const today = new Date().toISOString().split("T")[0];

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      const res1 = await fetch(`/api/day/${today}`);
      const json = await res1.json();
      setSummary(json.summary);
      setEntries(json.entries);
      setLoading(false);
    }
    fetchData();
  }, [today]);

  if (loading) return <div className="p-4">Loading...</div>;

  return (
    <div className="p-4 space-y-4">
      {summary && <SummaryPanel summary={summary} />}
      <Timeline entries={entries} />
    </div>
  );
}
