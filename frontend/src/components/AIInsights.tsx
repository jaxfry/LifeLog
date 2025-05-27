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
    <div className="h-full flex flex-col overflow-hidden w-full">
      <div className="flex items-center gap-2 p-4 border-b border-gray-100">
        <div className="text-indigo-600">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
            <path d="M11.645 20.91l-.007-.003-.022-.012a15.247 15.247 0 01-.383-.218 25.18 25.18 0 01-4.244-3.17C4.688 15.36 2.25 12.174 2.25 8.25 2.25 5.322 4.714 3 7.688 3A5.5 5.5 0 0112 5.052 5.5 5.5 0 0116.313 3c2.973 0 5.437 2.322 5.437 5.25 0 3.925-2.438 7.111-4.739 9.256a25.175 25.175 0 01-4.244 3.17 15.247 15.247 0 01-.383.219l-.022.012-.007.004-.003.001a.752.752 0 01-.704 0l-.003-.001z" />
          </svg>
        </div>
        <h2 className="text-xl font-semibold">AI Insights</h2>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4">
        <div className="mb-6">
          <h3 className="text-lg font-medium mb-2">Daily Summary</h3>
          <p className="text-gray-600">{day_summary}</p>
        </div>
        
        <div className="bg-gray-50 rounded-lg p-4 mb-6">
          <p className="text-sm text-gray-600 leading-relaxed">
            You spent {stats.total_active_time_min > 0 ? 
              `${Math.floor(stats.total_active_time_min / 60)}h ${stats.total_active_time_min % 60}m` : 
              'some time'} today, primarily on {stats.top_activity || 'various activities'}.
            {stats.focus_time_min > 120 ? ' Your balance of work and breaks supports sustained productivity.' : ''}
          </p>
        </div>
        
        <div className="mb-6">
          <h3 className="text-lg font-medium mb-3">Top Activities</h3>
          <div className="space-y-3">
            {topActivities.map((activity) => (
              <div 
                key={activity.name}
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50"
              >
                <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center">
                  <span className="text-sm font-medium text-indigo-600">
                    {activity.name.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div className="flex-1 flex justify-between">
                  <span className="font-medium">{activity.name}</span>
                  <span className="text-gray-500">{activity.duration}m</span>
                </div>
              </div>
            ))}
          </div>
        </div>
        
        <div className="mb-6">
          <h3 className="text-lg font-medium mb-3">Focus Time</h3>
          <div className="bg-gray-50 rounded-lg p-4 flex items-center">
            <div className="text-2xl font-bold text-green-600">
              {Math.floor(stats.focus_time_min / 60)}h {stats.focus_time_min % 60}m
            </div>
            <div className="ml-3 text-sm text-gray-600">
              {stats.focus_time_min > 300 ? 'Amazing focus today!' : 
               stats.focus_time_min > 180 ? 'Great focus today!' : 
               stats.focus_time_min > 60 ? 'Good focus session!' : 
               'Keep building your focus!'}
            </div>
          </div>
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-white rounded-lg border border-gray-100 p-3">
            <div className="text-sm text-gray-500 mb-1">Active time</div>
            <div className="text-xl font-semibold">
              {stats.total_active_time_min} min
            </div>
          </div>
          
          <div className="bg-white rounded-lg border border-gray-100 p-3">
            <div className="text-sm text-gray-500 mb-1">Focus time</div>
            <div className="text-xl font-semibold">
              {stats.focus_time_min} min
            </div>
          </div>
          
          <div className="bg-white rounded-lg border border-gray-100 p-3">
            <div className="text-sm text-gray-500 mb-1">Top project</div>
            <div className="text-xl font-semibold truncate">
              {stats.top_project}
            </div>
          </div>
          
          <div className="bg-white rounded-lg border border-gray-100 p-3">
            <div className="text-sm text-gray-500 mb-1">Top activity</div>
            <div className="text-xl font-semibold truncate">
              {stats.top_activity}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
