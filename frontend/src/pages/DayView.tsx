import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useDayData } from "../hooks/useDayData";
import Timeline from "../features/Timeline";
import SummaryPanel from "../features/SummaryPanel";
import { Input } from "../components/ui";

/* ────────────────────────────────────────────────────────────────────────── */
/*  Main component                                                           */
/* ────────────────────────────────────────────────────────────────────────── */
export default function DayView() {
  /* ----- routing & fetch ------------------------------------------------- */
  const { day = "" } = useParams<{ day: string }>();
  const navigate = useNavigate();
  const { data, loading, error } = useDayData(day);

  /* ----- build tag list from data --------------------------------------- */
  const tagOptions = useMemo(() => {
    const set = new Set<string>();
    data?.entries.forEach((e: any) => e.tags?.forEach((t: string) => set.add(t)));
    return ["All", ...Array.from(set).sort()];
  }, [data]);

  /* ----- UI state: active tag ------------------------------------------- */
  const [activeTag, setActiveTag] = useState<string>("All");
  useEffect(() => {
    if (!tagOptions.includes(activeTag)) setActiveTag("All");
  }, [tagOptions, activeTag]);

  /* ----- navigate on date change ---------------------------------------- */
  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) =>
    navigate(`/day/${e.target.value}`);

  /* ----- filter + SORT entries ------------------------------------------ */
  const filteredEntries =
    activeTag === "All"
      ? data?.entries || []
      : (data?.entries || []).filter((e: any) => e.tags?.includes(activeTag));

  const sortedEntries = [...filteredEntries].sort(
    (a, b) => new Date(a.start).getTime() - new Date(b.start).getTime()
  );

  /* ----- loading / error / empty states --------------------------------- */
  if (loading) return <CenteredMessage>Loading…</CenteredMessage>;

  if (error)
    return (
      <EmptyState
        message={error}
        actionLabel="Back to Home"
        action={() => navigate("/")}
      />
    );

  if (!data || data.entries.length === 0)
    return (
      <EmptyState
        message={`No data found for ${day}. Try another date.`}
        actionLabel="Back to Home"
        action={() => navigate("/")}
      />
    );

  /* ----- main layout ----------------------------------------------------- */
  return (
    <div className="h-screen w-full bg-surface-secondary text-primary overflow-hidden">
      <div className="flex flex-col h-full">
        {/* Top bar with tags and search */}
        <header className="flex items-center justify-between p-4 bg-surface-primary shadow-sm">
          <nav aria-label="Filter activities by tags">
            <div className="flex flex-wrap gap-2" role="group">
              {tagOptions.map((tag) => (
                <button
                  key={tag}
                  onClick={() => setActiveTag(tag)}
                  className={`px-3 py-1 rounded-full text-sm border focus:outline-none transition-colors focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 ${
                    activeTag === tag
                      ? "bg-primary-600 text-on-primary border-primary-600"
                      : "text-on-surface-dark bg-surface-primary border-surface-light hover:bg-surface-secondary"
                  }`}
                  aria-pressed={activeTag === tag}
                  aria-label={`Filter by ${tag} activities`}
                >
                  {tag}
                </button>
              ))}
            </div>
          </nav>
        </header>

        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar */}
          <aside 
            className="w-full max-w-md p-6 border-r border-light overflow-y-auto bg-surface-primary shadow-sm space-y-6"
            aria-label="Day information and summary"
          >
            {/* Date picker */}
            <section>
              <label className="block text-sm font-medium mb-1 text-primary" htmlFor="date-picker">
                Select date
              </label>
              <Input
                id="date-picker"
                type="date"
                value={day}
                onChange={handleDateChange}
                className="w-full px-3 py-2 border rounded-md text-sm"
                aria-describedby="date-picker-help"
              />
              <p id="date-picker-help" className="sr-only">
                Change the date to view activities for a different day
              </p>
            </section>

            {/* Daily Summary */}
            {data?.summary && <SummaryPanel summary={data.summary} />}
          </aside>

          {/* Timeline column */}
          <main className="flex-1 p-6 overflow-y-auto" role="main" aria-label="Daily timeline">
            <header className="text-center mb-6">
              <h1 className="text-2xl font-bold text-primary">
                Daily Timeline
              </h1>
              <p className="text-sm text-secondary mt-2">
                {sortedEntries.length} activities on {new Date(day).toLocaleDateString()}
              </p>
            </header>
            
            <Timeline
              entries={sortedEntries.map((entry) => ({
                ...entry,
                color:
                  entry.tags?.includes("Work")
                    ? "bg-success-500"
                    : entry.tags?.includes("Break")
                    ? "bg-warning-500"
                    : "bg-surface-light",
              }))}
            />
          </main>
        </div>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Helper components                                                         */
/* ────────────────────────────────────────────────────────────────────────── */
function CenteredMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-secondary">
      <p className="text-secondary">{children}</p>
    </div>
  );
}

function EmptyState(props: {
  message: string;
  actionLabel: string;
  action: () => void;
}) {
  return (
    <main className="min-h-screen flex items-center justify-center bg-surface-secondary" role="main">
      <div className="bg-surface-primary shadow-md rounded-xl p-8 space-y-6 text-center max-w-md">
        <p className="text-secondary">{props.message}</p>
        <button
          onClick={props.action}
          className="px-4 py-2 bg-primary-600 text-on-primary rounded-lg hover:bg-primary-700 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
        >
          {props.actionLabel}
        </button>
      </div>
    </main>
  );
}
