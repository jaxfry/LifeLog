import SummaryPanel from "../SummaryPanel";
import { useDayData } from "../../hooks/useDayData";

export default function DailySummaryWidget() {
  const { data, loading, error } = useDayData("2025-05-22");

  if (loading) {
    return (
      <section className="border-card bg-secondary p-4 shadow-card">
        <p className="text-secondary">Loading summary...</p>
      </section>
    );
  }

  if (error || !data) {
    return (
      <section className="border-card bg-secondary p-4 shadow-card">
        <p className="text-secondary">Failed to load summary.</p>
      </section>
    );
  }

  return <SummaryPanel summary={data.summary} />;
}
