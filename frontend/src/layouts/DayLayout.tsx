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
  
  // Filter entries based on activeFilter
  const filteredEntries = useMemo(() => {
    if (!data?.entries) return [];
    
    if (activeFilter === 'All') {
      return data.entries;
    }
    
    return data.entries.filter(entry => 
      entry.tags?.includes(activeFilter) || 
      entry.activity === activeFilter
    );
  }, [data?.entries, activeFilter]);
  
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
    <div className="h-full w-full flex overflow-hidden timeflow-ui" style={{ backgroundColor: 'var(--color-neutral-950)' }}>
      {/* Left Sidebar - Fixed width */}
      <aside className="w-72 flex-shrink-0 text-on-surface-dark flex flex-col h-full border-r border-outline-light" aria-label="Application sidebar">
        {/* Logo and app name */}
        <header className="p-5 flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-primary-600 flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5" aria-hidden="true">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"></path>
            </svg>
          </div>
          <h1 className="text-xl font-semibold">TimeFlow</h1>
        </header>
        
        <p className="text-on-surface-light text-sm px-5">Your intelligent activity journal</p>
        
        {/* Calendar */}
        <nav className="mt-6 px-5" aria-label="Date navigation">
          <div className="flex flex-col mb-4">
            <h2 className="text-lg font-medium text-on-surface-dark">
              {parseDateFromParam(day).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
            </h2>
            <div className="flex justify-between items-center mt-2">
              <div className="flex gap-2">
                <button 
                  className="w-6 h-6 flex items-center justify-center rounded nav-button"
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
                  className="w-6 h-6 flex items-center justify-center rounded nav-button"
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
              <div key={`weekday-${index}`} className="text-on-surface-light text-xs">{day}</div>
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
                    <div key={`empty-${i}`} className="h-6"></div>
                  ))}
                  
                  {/* Days */}
                  {days.map(dayNum => {
                    const isActive = dayNum === currentDay;
                    const dayString = dayNum.toString().padStart(2, '0');
                    const dateString = `${year}-${String(month + 1).padStart(2, '0')}-${dayString}`;
                    
                    return (
                      <button
                        key={dayNum}
                        className={`h-7 w-7 rounded-full flex items-center justify-center mx-auto text-sm calendar-button
                          ${isActive ? 'calendar-day-active' : 'calendar-day-inactive'}`}
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
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 flex items-center justify-center rounded-full bg-success-500">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-on-success" aria-hidden="true">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"></path>
                </svg>
              </div>
              <p className="text-sm text-on-surface-light">Today's Focus</p>
            </div>
            <div className="mt-2 text-2xl font-bold text-on-surface-dark">
              {data.summary.stats.focus_time_min > 0 ? 
                `${Math.floor(data.summary.stats.focus_time_min / 60)}h ${data.summary.stats.focus_time_min % 60}m` : 
                '0h 0m'}
            </div>
          </div>
          
          {/* Break Time */}
          <div className="p-5 border-t border-outline-light">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 flex items-center justify-center text-warning-400">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5" aria-hidden="true">
                  <path d="M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"></path>
                </svg>
              </div>
              <p className="text-sm text-on-surface-light">Break Time</p>
            </div>
            <div className="mt-2 text-2xl font-bold text-on-surface-dark">
              {/* Calculate break time as the difference between total active time and focus time */}
              {data.summary.stats.total_active_time_min > data.summary.stats.focus_time_min ? 
                `${Math.floor((data.summary.stats.total_active_time_min - data.summary.stats.focus_time_min) / 60)}h ${(data.summary.stats.total_active_time_min - data.summary.stats.focus_time_min) % 60}m` : 
                '0h 0m'}
            </div>
          </div>
        </section>
      </aside>

      {/* Main Content */}
      <main className="flex flex-1 overflow-auto flex-col" style={{ backgroundColor: 'var(--background-secondary)' }} role="main">
        {/* Top bar above both timeline and AI Insights */}
        <TimelineTopBar 
          formattedDate={getFormattedTimelineDate(day ? parseDateFromParam(day) : undefined)}
          activeFilter={activeFilter}
          onFilterChange={setActiveFilter}
        />
        <div className="flex flex-1 min-h-0">
          {/* Timeline section - Will grow to fill available space */}
          <section className="flex-1 min-w-0 overflow-auto" aria-label="Activity timeline">
            <Timeline 
              entries={filteredEntries}
            />
          </section>
          {/* Right sidebar - AI Insights with fixed width */}
          <aside className="w-80 flex-shrink-0 overflow-y-auto flex flex-col h-full" style={{ backgroundColor: 'var(--background-secondary)', border: 'none' }} aria-label="AI insights">
            <header className="p-4">
              <h2 className="text-lg font-semibold text-text-primary">AI Insights</h2>
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
