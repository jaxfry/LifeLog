import { DailySummary } from "../types";

export default function SummaryPanel({ summary }: { summary: DailySummary }) {
  const { day_summary, stats } = summary;

  return (
    <div className="border rounded-xl p-4 shadow">
      <h2 className="text-xl font-bold mb-2">Daily Summary</h2>
      <p className="mb-3">{day_summary}</p>
      <ul className="text-sm text-gray-600 grid grid-cols-2 gap-2">
        <li><strong>Active Time:</strong> {stats.total_active_time_min} min</li>
        <li><strong>Focus Time:</strong> {stats.focus_time_min} min</li>
        <li><strong>Blocks:</strong> {stats.number_blocks}</li>
        <li><strong>Top Project:</strong> {stats.top_project}</li>
        <li><strong>Top Activity:</strong> {stats.top_activity}</li>
      </ul>
    </div>
  );
}
