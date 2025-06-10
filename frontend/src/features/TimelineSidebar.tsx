import { useNavigate, useParams } from "react-router-dom";
import { useDayData } from "../hooks/useDayData";

interface TimelineSidebarProps {
  collapsed?: boolean;
}

function parseDateFromParam(dateStr: string) {
  if (!dateStr) return new Date();
  const parts = dateStr.split("-");
  if (parts.length === 3) {
    const [year, month, day] = parts.map(Number);
    return new Date(year, month - 1, day);
  }
  return new Date();
}

export default function TimelineSidebar({ collapsed }: TimelineSidebarProps) {
  const { day = "" } = useParams<{ day: string }>();
  const navigate = useNavigate();
  const { data } = useDayData(day);

  const date = parseDateFromParam(day);

  const focus = data?.summary.stats.focus_time_min ?? 0;
  const breakMinutes = Math.max(0, (data?.summary.stats.total_active_time_min ?? 0) - focus);

  return (
    <div className="px-5 pb-5">
      {/* Calendar Header */}
      {!collapsed && (
        <div className="flex flex-col mb-4">
          <h2 className="type-h3 text-primary">
            {date.toLocaleDateString("en-US", { month: "long", year: "numeric" })}
          </h2>
          <div className="flex justify-between items-center mt-3">
            <div className="flex gap-2">
              <button
                className="w-8 h-8 flex items-center justify-center rounded-lg bg-tertiary hover:bg-tertiary/80 text-primary transition-hover focus-ring"
                onClick={() => {
                  const current = new Date(date);
                  current.setDate(current.getDate() - 1);
                  navigate(`/day/${current.toISOString().slice(0, 10)}`);
                }}
                aria-label="Previous day"
              >
                ‹
              </button>
              <button
                className="w-8 h-8 flex items-center justify-center rounded-lg bg-tertiary hover:bg-tertiary/80 text-primary transition-hover focus-ring"
                onClick={() => {
                  const current = new Date(date);
                  current.setDate(current.getDate() + 1);
                  navigate(`/day/${current.toISOString().slice(0, 10)}`);
                }}
                aria-label="Next day"
              >
                ›
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Calendar Grid */}
      {!collapsed && (
        <div className="grid grid-cols-7 gap-y-2 text-center" aria-label="Calendar">
          {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => (
            <div key={`weekday-${i}`} className="type-caption text-secondary">
              {d}
            </div>
          ))}
          {(() => {
            const year = date.getFullYear();
            const month = date.getMonth();
            const firstDay = new Date(year, month, 1);
            const firstWeekday = firstDay.getDay();
            const lastDay = new Date(year, month + 1, 0);
            const daysInMonth = lastDay.getDate();
            const currentDay = date.getDate();
            const empty = Array(firstWeekday).fill(null);
            const days = Array.from({ length: daysInMonth }, (_, i) => i + 1);
            return (
              <>
                {empty.map((_, i) => (
                  <div key={`empty-${i}`} className="h-8" />
                ))}
                {days.map(dNum => {
                  const isActive = dNum === currentDay;
                  const dStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(dNum).padStart(2, '0')}`;
                  return (
                    <button
                      key={dNum}
                      className={`h-8 w-8 rounded-full flex items-center justify-center mx-auto text-sm transition-hover focus-ring font-mono ${isActive ? 'calendar-day-active' : 'calendar-day-inactive text-primary hover:bg-tertiary/50'}`}
                      onClick={() => navigate(`/day/${dStr}`)}
                      aria-label={`Select ${dNum}`}
                      aria-current={isActive ? 'date' : undefined}
                    >
                      {dNum}
                    </button>
                  );
                })}
              </>
            );
          })()}
        </div>
      )}

      {/* Stats */}
      {!collapsed && (
        <section className="mt-6" aria-label="Daily statistics">
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
                  {focus > 0 ? `${Math.floor(focus / 60)}h ${focus % 60}m` : '0h 0m'}
                </div>
              </div>
            </div>
          </div>
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
                  {`${Math.floor(breakMinutes / 60)}h ${breakMinutes % 60}m`}
                </div>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

