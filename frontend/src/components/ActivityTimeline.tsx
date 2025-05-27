import { useState, useMemo } from 'react';
import { formatDuration, formatTime } from '../lib/utils';
import ActivityIcon from './ui/ActivityIcon';
import type { TimelineEntry } from '../types';

interface ActivityCardProps {
  entry: TimelineEntry;
  className?: string;
}

function ActivityCard({ entry, className = "" }: ActivityCardProps) {
  const start = new Date(entry.start);
  const end = new Date(entry.end);
  const duration = formatDuration(start, end);

  return (
    <div className={`flex rounded-lg border border-gray-100 shadow-sm overflow-hidden ${className}`} style={{ backgroundColor: '#0F1727' }}>
      <div className="p-4 flex-1">
        <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
          <div>{formatTime(start)} - {formatTime(end)}</div>
          <div className="font-medium">{duration}</div>
        </div>

        <div className="flex gap-3">
          <ActivityIcon activity={entry.activity} size="md" />
          
          <div className="flex-1">
            <h3 className="font-medium text-base text-white">{entry.activity}</h3>
            <p className="text-sm text-gray-400 line-clamp-2 mt-0.5">
              {entry.summary || entry.label}
            </p>
            
            {entry.tags && entry.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2" style={{ backgroundColor: '#020412' }}>
                {entry.tags.map(tag => (
                  <span 
                    key={tag}
                    className="px-2 py-0.5 text-xs rounded-full"
                    style={{
                      backgroundColor: getTagColor(tag).bg,
                      color: getTagColor(tag).text
                    }}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function getTagColor(tag: string) {
  const colors: Record<string, { bg: string, text: string }> = {
    'Work': { bg: '#e6f1ff', text: '#0969da' },
    'Creative': { bg: '#fdf4e8', text: '#953800' },
    'Communication': { bg: '#f6f8fa', text: '#57606a' },
    'Entertainment': { bg: '#ffeff7', text: '#bf3989' },
    'Productivity': { bg: '#dafbe1', text: '#1a7f37' },
    'All': { bg: '#f6f8fa', text: '#57606a' }
  };
  
  return colors[tag] || colors['All'];
}

export default function ActivityTimeline({ 
  entries, 
  selectedDate 
}: { 
  entries: TimelineEntry[];
  selectedDate?: Date;
}) {
  const [activeType, setActiveType] = useState<string>('All');
  
  // Generate activity types dynamically from entries
  const activityTypes = useMemo(() => {
    const uniqueActivities = new Set<string>();
    
    // Extract unique activities from entries
    entries.forEach(entry => {
      if (entry.activity) {
        uniqueActivities.add(entry.activity);
      }
      // Also include tags as activity types
      if (entry.tags && Array.isArray(entry.tags)) {
        entry.tags.forEach(tag => uniqueActivities.add(tag));
      }
    });
    
    // Create an array with "All" first, then sorted activities
    return [
      {id: 'All', label: 'All'},
      ...Array.from(uniqueActivities)
        .sort()
        .map(activity => ({id: activity, label: activity}))
    ];
  }, [entries]);

  const filteredEntries = activeType === 'All' 
    ? entries 
    : entries.filter(entry => 
        entry.tags?.includes(activeType) || 
        entry.activity === activeType
      );

  // Format the selected date for display
  const formattedDate = selectedDate ? selectedDate.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }) : new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });

  // Only the filter bar and timeline list remain here
  return (
    <div className="h-full flex flex-col overflow-hidden" style={{ backgroundColor: '#020412' }}>
      <div className="p-3 flex gap-2 overflow-x-auto border-b border-gray-100 bg-white">
        {activityTypes.map(type => (
          <button
            key={type.id}
            className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap ${
              activeType === type.id 
                ? 'bg-gray-900 text-white' 
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
            onClick={() => setActiveType(type.id)}
          >
            {type.label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {filteredEntries.map((entry, index) => (
          <ActivityCard key={index} entry={entry} />
        ))}
      </div>
    </div>
  );
}

export function getFormattedTimelineDate(selectedDate?: Date) {
  return selectedDate ? selectedDate.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }) : new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
}
