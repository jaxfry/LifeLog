import { useMemo } from 'react';
import type { DailySummary, TimelineEntry } from '../types';

interface AIInsightsProps {
  summary: DailySummary;
  entries?: TimelineEntry[];
}

export default function AIInsights({ summary, entries = [] }: AIInsightsProps) {
  const { day_summary, stats } = summary;
  
  // Calculate top activities from actual entries
  const topActivities = useMemo(() => {
    // Group entries by activity and calculate total duration
    const activityMap = new Map<string, number>();
    
    entries.forEach(entry => {
      const activity = entry.activity;
      const start = new Date(entry.start);
      const end = new Date(entry.end);
      const durationMs = end.getTime() - start.getTime();
      
      const currentDuration = activityMap.get(activity) || 0;
      activityMap.set(activity, currentDuration + durationMs);
    });
    
    // Convert to array, sort by duration, and take top 3
    return Array.from(activityMap.entries())
      .map(([name, durationMs]) => ({
        name,
        duration: Math.floor(durationMs / 60000) // Convert to minutes
      }))
      .sort((a, b) => b.duration - a.duration)
      .slice(0, 3);
  }, [entries]);

  return (
    <aside 
      className="h-full flex flex-col overflow-hidden w-full bg-surface-primary" 
      aria-label="AI-generated insights and statistics"
    >
      
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        <section className="mb-6" aria-labelledby="daily-summary-heading">
          <h3 id="daily-summary-heading" className="text-lg font-medium mb-2 text-primary">Daily Summary</h3>
          <p className="text-secondary leading-relaxed">{day_summary}</p>
        </section>
        
        <section className="mb-6" aria-labelledby="top-activities-heading">
          <h3 id="top-activities-heading" className="text-lg font-medium mb-3 text-primary">Top Activities</h3>
          <ul className="space-y-3" role="list" aria-label="List of most time-consuming activities">
            {topActivities.map((activity) => (
              <li 
                key={activity.name}
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-surface-tertiary transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center" aria-hidden="true">
                  <span className="text-sm font-medium text-primary-700">
                    {activity.name.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div className="flex-1 flex justify-between">
                  <span className="font-medium text-primary">{activity.name}</span>
                  <span className="text-secondary" aria-label={`${activity.duration} minutes`}>{activity.duration}m</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
        
        <section className="mb-6" aria-labelledby="focus-time-heading">
          <h3 id="focus-time-heading" className="text-lg font-medium mb-3 text-primary">Focus Time</h3>
          <div className="bg-surface-secondary rounded-lg p-4 flex items-center">
            <div className="text-2xl font-bold text-success-600">
              {Math.floor(stats.focus_time_min / 60)}h {stats.focus_time_min % 60}m
            </div>
            <div className="ml-3 text-sm text-secondary">
              {stats.focus_time_min > 300 ? 'Amazing focus today!' : 
               stats.focus_time_min > 180 ? 'Great focus today!' : 
               stats.focus_time_min > 60 ? 'Good focus session!' : 
               'Keep building your focus!'}
            </div>
          </div>
        </section>
        
        <section aria-labelledby="statistics-heading">
          <h3 id="statistics-heading" className="sr-only">Daily Statistics</h3>
          <div className="grid grid-cols-2 gap-4" role="group" aria-label="Daily activity statistics">
            <div className="bg-surface-primary rounded-lg border border-light p-3">
              <div className="text-sm text-secondary mb-1">Active time</div>
              <div className="text-xl font-semibold text-primary">
                {stats.total_active_time_min} min
              </div>
            </div>
            
            <div className="bg-surface-primary rounded-lg border border-light p-3">
              <div className="text-sm text-secondary mb-1">Focus time</div>
              <div className="text-xl font-semibold text-primary">
                {stats.focus_time_min} min
              </div>
            </div>
            
            <div className="bg-surface-primary rounded-lg border border-light p-3">
              <div className="text-sm text-secondary mb-1">Top project</div>
              <div className="text-xl font-semibold truncate text-primary">
                {stats.top_project}
              </div>
            </div>
            
            <div className="bg-surface-primary rounded-lg border border-light p-3">
              <div className="text-sm text-secondary mb-1">Top activity</div>
              <div className="text-xl font-semibold truncate text-primary">
                {stats.top_activity}
              </div>
            </div>
          </div>
        </section>
      </div>
    </aside>
  );
}
