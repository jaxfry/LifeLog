import type { DailySummary } from "../types";

interface SummaryPanelProps {
  summary: DailySummary;
}

export default function SummaryPanel({ summary }: SummaryPanelProps) {
  const { day_summary, stats } = summary;

  return (
    <section 
      className="rounded-lg shadow p-6 border border-light bg-surface-primary"
      aria-labelledby="daily-summary-heading"
    >
      <header>
        <h2 id="daily-summary-heading" className="text-xl font-semibold mb-3 text-primary">
          Daily Summary
        </h2>
      </header>
      
      <div className="text-sm text-primary mb-4 leading-relaxed whitespace-pre-line">
        {day_summary}
      </div>

      <div className="space-y-4">
        <h3 className="sr-only">Daily Statistics</h3>
        
        <div className="grid grid-cols-2 gap-y-3 text-sm" role="group" aria-label="Daily activity statistics">
          <div className="flex justify-between">
            <span className="font-medium text-secondary">Active time:</span>
            <span className="text-primary" aria-label={`${stats.total_active_time_min} minutes of active time`}>
              {stats.total_active_time_min} min
            </span>
          </div>
          
          <div className="flex justify-between">
            <span className="font-medium text-secondary">Focus time:</span>
            <span className="text-primary" aria-label={`${stats.focus_time_min} minutes of focus time`}>
              {stats.focus_time_min} min
            </span>
          </div>
          
          <div className="flex justify-between">
            <span className="font-medium text-secondary">Blocks:</span>
            <span className="text-primary" aria-label={`${stats.number_blocks} activity blocks`}>
              {stats.number_blocks}
            </span>
          </div>
          
          {stats.top_project && (
            <div className="flex justify-between">
              <span className="font-medium text-secondary">Top project:</span>
              <span className="text-primary" title={`Most active project: ${stats.top_project}`}>
                {stats.top_project}
              </span>
            </div>
          )}
          
          {stats.top_activity && (
            <div className="flex justify-between">
              <span className="font-medium text-secondary">Top activity:</span>
              <span className="text-primary" title={`Most frequent activity: ${stats.top_activity}`}>
                {stats.top_activity}
              </span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
