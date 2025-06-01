import type { DailySummary } from "../types";

interface SummaryPanelProps {
  summary: DailySummary;
}

export default function SummaryPanel({ summary }: SummaryPanelProps) {
  const { day_summary, stats } = summary;

  return (
    <section 
      className="border-card bg-secondary p-6 shadow-card"
      aria-labelledby="daily-summary-heading"
    >
      <header>
        <h2 id="daily-summary-heading" className="type-h3 mb-4 text-primary">
          Daily Summary
        </h2>
      </header>
      
      <div className="type-body text-primary mb-6 leading-relaxed whitespace-pre-line">
        {day_summary}
      </div>

      <div className="space-y-4">
        <h3 className="sr-only">Daily Statistics</h3>
        
        <div className="grid grid-cols-2 gap-y-4 gap-x-6" role="group" aria-label="Daily activity statistics">
          <div className="flex justify-between">
            <span className="type-caption text-secondary">Active time:</span>
            <span className="font-mono text-accent-500 font-medium" aria-label={`${stats.total_active_time_min} minutes of active time`}>
              {stats.total_active_time_min} min
            </span>
          </div>
          
          <div className="flex justify-between">
            <span className="type-caption text-secondary">Focus time:</span>
            <span className="font-mono text-accent-500 font-medium" aria-label={`${stats.focus_time_min} minutes of focus time`}>
              {stats.focus_time_min} min
            </span>
          </div>
          
          <div className="flex justify-between">
            <span className="type-caption text-secondary">Blocks:</span>
            <span className="font-mono text-accent-500 font-medium" aria-label={`${stats.number_blocks} activity blocks`}>
              {stats.number_blocks}
            </span>
          </div>
          
          {stats.top_project && (
            <div className="flex justify-between">
              <span className="type-caption text-secondary">Top project:</span>
              <span className="text-primary font-medium" title={`Most active project: ${stats.top_project}`}>
                {stats.top_project}
              </span>
            </div>
          )}
          
          {stats.top_activity && (
            <div className="flex justify-between">
              <span className="type-caption text-secondary">Top activity:</span>
              <span className="text-primary font-medium" title={`Most frequent activity: ${stats.top_activity}`}>
                {stats.top_activity}
              </span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
