import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useDayData } from '../hooks/useDayData';
import Timeline from '../components/Timeline';
import { getFormattedTimelineDate } from '../shared/utils';
import AIInsights from '../components/AIInsights';
import TimelineTopBar from '../components/TimelineTopBar';
import { CenteredMessage, EmptyState } from '../components/ui/StatusMessages'; // Import from ui components

export default function DayLayout() {
  const { day = "" } = useParams<{ day: string }>();
  const navigate = useNavigate();
  const { data, loading, error } = useDayData(day);
  
  // Add filter state management
  const [activeFilter, setActiveFilter] = useState<string>('All');
  // Add search query state
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Filter entries based on activeFilter and searchQuery
  const filteredEntries = useMemo(() => {
    if (!data?.entries) return [];
    let entries = data.entries;
    if (activeFilter !== 'All') {
      entries = entries.filter(entry => 
        entry.tags?.includes(activeFilter) || 
        entry.activity === activeFilter
      );
    }
    if (searchQuery.trim() !== '') {
      const q = searchQuery.trim().toLowerCase();
      entries = entries.filter(entry =>
        entry.activity.toLowerCase().includes(q) ||
        entry.label?.toLowerCase().includes(q) ||
        entry.summary?.toLowerCase().includes(q) ||
        entry.notes?.toLowerCase().includes(q) ||
        (entry.tags && entry.tags.some(tag => tag.toLowerCase().includes(q)))
      );
    }
    return entries;
  }, [data?.entries, activeFilter, searchQuery]);
  
  // Parse date consistently to avoid timezone issues
  const parseDateFromParam = (dateStr: string) => {
    if (!dateStr) return new Date(); // Default to today if no date string
    const parts = dateStr.split('-');
    if (parts.length === 3) {
      const [year, month, dayOfMonth] = parts.map(Number);
      // Ensure month is 0-indexed for Date constructor
      return new Date(year, month - 1, dayOfMonth); 
    }
    return new Date(); // Fallback to today if format is unexpected
  };

  /* ----- loading / error / empty states --------------------------------- */
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
        action={() => navigate("/")}
      />
    </div>
  );

  if (!data || data.entries.length === 0) return (
    <div className="h-screen flex">
      <EmptyState
        message={`No data found for ${day}. Try another date.`}
        actionLabel="Back to Home"
        action={() => navigate("/")}
      />
    </div>
  );

  /* ----- main layout ----------------------------------------------------- */
  return (
    <div className="h-full w-full flex overflow-hidden bg-primary">
      {/* Left Sidebar - Fixed width */}
      <aside className="w-72 flex-shrink-0 bg-secondary text-primary flex flex-col h-full border-r border-light" aria-label="Application sidebar">
        {/* Logo and app name */}
        <header className="p-5 flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-accent-gradient flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5 text-inverse" aria-hidden="true">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"></path>
            </svg>
          </div>
          <h1 className="type-h3">LifeLog</h1>
        </header>
        
        <p className="type-caption text-secondary px-5 mb-6">Your digital life, beautifully organized</p>
        
        {/* Calendar */}
        <nav className="mt-6 px-5" aria-label="Date navigation">
          <div className="flex flex-col mb-4">
            <h2 className="type-h3 text-primary">
              {parseDateFromParam(day).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
            </h2>
            <div className="flex justify-between items-center mt-3">
              <div className="flex gap-2">
                <button 
                  className="w-8 h-8 flex items-center justify-center rounded-lg bg-tertiary hover:bg-tertiary/80 text-primary transition-hover focus-ring"
                  onClick={() => {
                    const currentDate = parseDateFromParam(day);
                    currentDate.setDate(currentDate.getDate() - 1);
                    navigate(`/day/${currentDate.toISOString().slice(0, 10)}`);
                  }}
                  aria-label="Previous day"
                >
                  ‹
                </button>
                <button 
                  className="w-8 h-8 flex items-center justify-center rounded-lg bg-tertiary hover:bg-tertiary/80 text-primary transition-hover focus-ring"
                  onClick={() => {
                    const currentDate = parseDateFromParam(day);
                    currentDate.setDate(currentDate.getDate() + 1);
                    navigate(`/day/${currentDate.toISOString().slice(0, 10)}`);
                  }}
                  aria-label="Next day"
                >
                  ›
                </button>
              </div>
            </div>
          </div>
          
          {/* Calendar grid */}
          <div className="grid grid-cols-7 gap-y-2 text-center">
            {/* Weekday headers */}
            {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((day, index) => (
              <div key={`weekday-${index}`} className="type-caption text-secondary">{day}</div>
            ))}
            
            {/* Generate calendar days */}
            {(() => {
              const date = parseDateFromParam(day); // Use parseDateFromParam here
              const year = date.getFullYear();
              const month = date.getMonth();
              
              // First day of the month
              const firstDay = new Date(year, month, 1);
              const firstDayOfWeek = firstDay.getDay(); // 0 = Sunday, 1 = Monday, ...
              
              // Last day of the month
              const lastDay = new Date(year, month + 1, 0);
              const daysInMonth = lastDay.getDate();
              
              // Current day
              const currentDay = date.getDate();
              
              // Empty spaces before the first day of the month
              const emptySpaces = Array(firstDayOfWeek).fill(null);
              
              // Days of the month
              const days = Array.from({ length: daysInMonth }, (_, i) => i + 1);
              
              return (
                <>
                  {/* Empty spaces */}
                  {emptySpaces.map((_, i) => (
                    <div key={`empty-${i}`} className="h-8"></div>
                  ))}
                  
                  {/* Days */}
                  {days.map(dayNum => {
                    const isActive = dayNum === currentDay;
                    const dayString = dayNum.toString().padStart(2, '0');
                    const dateString = `${year}-${String(month + 1).padStart(2, '0')}-${dayString}`;
                    
                    return (
                      <button
                        key={dayNum}
                        className={`h-8 w-8 rounded-full flex items-center justify-center mx-auto text-sm transition-hover focus-ring font-mono
                          ${isActive 
                            ? 'calendar-day-active' 
                            : 'calendar-day-inactive text-primary hover:bg-tertiary/50'
                          }`}
                        onClick={() => navigate(`/day/${dateString}`)}
                        aria-label={`Select ${dayNum}`}
                        aria-current={isActive ? 'date' : undefined}
                      >
                        {dayNum}
                      </button>
                    );
                  })}
                </>
              );
            })()}
          </div>
        </nav>
        
        {/* Focus Time */}
        <section className="mt-auto" aria-label="Daily statistics">
          <div className="p-5">
            <div className="flex items-center mb-3">
              <div className="w-10 h-10 flex items-center justify-center rounded-lg bg-success/20 border border-success/30 mr-1">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.25} stroke="currentColor" className="w-5 h-5 text-success" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="type-caption text-secondary">Focus Time</p>
                <div className="font-mono text-2xl font-bold text-primary">
                  {data.summary.stats.focus_time_min > 0 ? 
                    `${Math.floor(data.summary.stats.focus_time_min / 60)}h ${data.summary.stats.focus_time_min % 60}m` : 
                    '0h 0m'}
                </div>
              </div>
            </div>
          </div>
          
          {/* Break Time */}
          <div className="p-5 border-t border-light">
            <div className="flex items-center">
              <div className="w-10 h-10 flex items-center justify-center rounded-lg bg-warning/20 border border-warning/30 mr-1">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.25} stroke="currentColor" className="w-5 h-5 text-warning" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25a3 3 0 0 1 3 3m3 0a6 6 0 0 1-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1 1 21.75 8.25Z" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="type-caption text-secondary">Break Time</p>
                <div className="font-mono text-2xl font-bold text-primary">
                  {/* Calculate break time as the difference between total active time and focus time */}
                  {data.summary.stats.total_active_time_min > data.summary.stats.focus_time_min ? 
                    `${Math.floor((data.summary.stats.total_active_time_min - data.summary.stats.focus_time_min) / 60)}h ${(data.summary.stats.total_active_time_min - data.summary.stats.focus_time_min) % 60}m` : 
                    '0h 0m'}
                </div>
              </div>
            </div>
          </div>
        </section>
      </aside>

      {/* Main Content */}
      <main className="flex flex-1 overflow-auto flex-col bg-primary" role="main">
        {/* Top bar above both timeline and AI Insights */}
        <TimelineTopBar 
          formattedDate={getFormattedTimelineDate(day ? parseDateFromParam(day) : undefined)}
          activeFilter={activeFilter}
          onFilterChange={setActiveFilter}
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
        />
        <div className="flex flex-1 min-h-0">
          {/* Timeline section - Will grow to fill available space */}
          <section className="flex-1 min-w-0 overflow-auto" aria-label="Activity timeline">
            <Timeline 
              entries={filteredEntries}
            />
          </section>
          {/* Right sidebar - AI Insights with fixed width */}
          <aside className="w-80 flex-shrink-0 overflow-y-auto flex flex-col h-full bg-secondary border-l border-light" aria-label="AI insights">
            <header className="p-6 border-b border-light">
              <h2 className="type-h3 text-primary">AI Insights</h2>
            </header>
            <div className="flex-1 overflow-y-auto">
              <AIInsights summary={data.summary} entries={data.entries} />
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
