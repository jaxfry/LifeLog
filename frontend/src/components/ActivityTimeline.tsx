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
    <div className={`flex rounded-lg border border-gray-100 shadow-sm overflow-hidden ${className} h-[125px]`} style={{ backgroundColor: '#0F101D' }}>
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
              <div className="flex flex-wrap gap-1 mt-2" style={{ backgroundColor: '#0F101D' }}>
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
  entries 
}: { 
  entries: TimelineEntry[];
}) {
  // Only the timeline list remains here - no filtering logic
  return (
    <div className="h-full flex flex-col overflow-hidden" style={{ backgroundColor: '#0F101D' }}>
      <div className="flex-1 overflow-y-auto p-[30px] space-y-5 bg-gradient-to-b from-[#0f111d] via-[#101226] to-[#1b0f17]">
        {entries.map((entry, index) => (
          <ActivityCard key={index} entry={entry} />
        ))}
      </div>
    </div>
  );
}

export function getFormattedTimelineDate(selectedDate?: Date) {
  return selectedDate ? selectedDate.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric'
  }) : new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric'
  });
}
