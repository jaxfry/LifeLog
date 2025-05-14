import type { DailySummary } from "../types";

export default function SummaryPanel({ summary }: { summary: DailySummary }) {
  const { day_summary, stats } = summary;

  return (
    <div className="rounded-2xl shadow p-6 border border-gray-100 bg-white">
      <h2 className="text-xl font-semibold mb-3 text-gray-800">Daily Summary</h2>
      <p className="text-sm text-gray-700 mb-4 leading-relaxed whitespace-pre-line">
        {day_summary}
      </p>

      <div className="grid grid-cols-2 gap-y-2 text-sm text-gray-600">
        <span className="font-medium">Active time:</span>
        <span>{stats.total_active_time_min} min</span>
        <span className="font-medium">Focus time:</span>
        <span>{stats.focus_time_min} min</span>
        <span className="font-medium">Blocks:</span>
        <span>{stats.number_blocks}</span>
        <span className="font-medium">Top project:</span>
        <span>{stats.top_project}</span>
        <span className="font-medium">Top activity:</span>
        <span>{stats.top_activity}</span>
      </div>
    </div>
  );
}
