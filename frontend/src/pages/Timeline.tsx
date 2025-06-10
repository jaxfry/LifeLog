import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useDayData } from '../hooks/useDayData';
import Timeline from '../features/Timeline';
import AIInsights from '../features/AIInsights';
import TimelineTopBar from '../features/TimelineTopBar';
import { CenteredMessage, EmptyState } from '../components/ui/StatusMessages';
import { getFormattedTimelineDate } from '../shared/utils';

export default function TimelinePage() {
  const { day = '' } = useParams<{ day: string }>();
  const navigate = useNavigate();
  const { data, loading, error } = useDayData(day);

  const [activeFilter, setActiveFilter] = useState<string>('All');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const filteredEntries = useMemo(() => {
    if (!data?.entries) return [];
    let entries = data.entries;
    if (activeFilter !== 'All') {
      entries = entries.filter((entry: any) =>
        entry.tags?.includes(activeFilter) ||
        entry.activity === activeFilter
      );
    }
    if (searchQuery.trim() !== '') {
      const q = searchQuery.trim().toLowerCase();
      entries = entries.filter((entry: any) =>
        entry.activity.toLowerCase().includes(q) ||
        entry.label?.toLowerCase().includes(q) ||
        entry.summary?.toLowerCase().includes(q) ||
        entry.notes?.toLowerCase().includes(q) ||
        (entry.tags && entry.tags.some((tag: string) => tag.toLowerCase().includes(q)))
      );
    }
    return entries;
  }, [data?.entries, activeFilter, searchQuery]);

  const parseDateFromParam = (dateStr: string) => {
    if (!dateStr) return new Date();
    const parts = dateStr.split('-');
    if (parts.length === 3) {
      const [year, month, dayOfMonth] = parts.map(Number);
      return new Date(year, month - 1, dayOfMonth);
    }
    return new Date();
  };

  if (loading) return (
    <div className="h-screen flex">
      <CenteredMessage>Loading…</CenteredMessage>
    </div>
  );

  if (error) return (
    <div className="h-screen flex">
      <EmptyState
        message={error}
        actionLabel="Back to Home"
        action={() => navigate('/')}
      />
    </div>
  );

  if (!data || data.entries.length === 0) return (
    <div className="h-screen flex">
      <EmptyState
        message={`No data found for ${day}. Try another date.`}
        actionLabel="Back to Home"
        action={() => navigate('/')}
      />
    </div>
  );

  return (
    <div className="flex flex-col h-full">
      <TimelineTopBar
        formattedDate={getFormattedTimelineDate(day ? parseDateFromParam(day) : undefined)}
        activeFilter={activeFilter}
        onFilterChange={setActiveFilter}
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
      />
      <div className="flex flex-1 min-h-0">
        <section className="flex-1 min-w-0 overflow-auto" aria-label="Activity timeline">
          <Timeline entries={filteredEntries} />
        </section>
        <aside className="w-80 flex-shrink-0 overflow-y-auto flex flex-col h-full bg-secondary border-l border-light" aria-label="AI insights">
          <header className="p-6 border-b border-light">
            <h2 className="type-h3 text-primary">AI Insights</h2>
          </header>
          <div className="flex-1 overflow-y-auto">
            <AIInsights summary={data.summary} entries={data.entries} />
          </div>
        </aside>
      </div>
    </div>
  );
}
