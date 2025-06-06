import { Clock, TrendingUp, Briefcase } from "lucide-react";
import { useDayData } from "../../hooks/useDayData";

export default function StatsWidget() {
  const { data, loading, error } = useDayData("2025-05-22");

  if (loading) {
    return (
      <section className="border-card bg-secondary p-4 shadow-card">
        <p className="text-secondary">Loading stats...</p>
      </section>
    );
  }

  if (error || !data) {
    return (
      <section className="border-card bg-secondary p-4 shadow-card">
        <p className="text-secondary">Failed to load stats.</p>
      </section>
    );
  }

  const {
    total_active_time_min,
    focus_time_min,
    number_blocks,
    top_project,
    top_activity,
  } = data.summary.stats;

  return (
    <section
      className="border-card bg-secondary p-4 shadow-card flex flex-col gap-4"
      aria-label="Daily stats"
    >
      <h2 className="text-lg font-semibold text-primary">Daily Stats</h2>
      <ul className="space-y-2">
        <li className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-secondary">
            <Clock className="h-4 w-4" /> Active
          </span>
          <span className="font-mono text-primary">
            {total_active_time_min} min
          </span>
        </li>
        <li className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-secondary">
            <TrendingUp className="h-4 w-4" /> Focus
          </span>
          <span className="font-mono text-primary">{focus_time_min} min</span>
        </li>
        <li className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-secondary">
            <Briefcase className="h-4 w-4" /> Blocks
          </span>
          <span className="font-mono text-primary">{number_blocks}</span>
        </li>
        {top_project && (
          <li className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-secondary">
              <Briefcase className="h-4 w-4" /> Project
            </span>
            <span className="text-primary">{top_project}</span>
          </li>
        )}
        {top_activity && (
          <li className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-secondary">
              <Briefcase className="h-4 w-4" /> Activity
            </span>
            <span className="text-primary">{top_activity}</span>
          </li>
        )}
      </ul>
    </section>
  );
}
