import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useDayData } from "../hooks/useDayData";
import SummaryPanel from "../components/SummaryPanel";
import Timeline from "../components/Timeline";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";

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
    data?.entries.forEach((e) => e.tags?.forEach((t) => set.add(t)));
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
      : (data?.entries || []).filter((e) => e.tags?.includes(activeTag));

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
    <div className="h-screen w-full bg-gray-50 text-gray-900 overflow-hidden">
      <div className="flex h-full">
        {/* ───────── Sidebar ─────────────────────────────────────────────── */}
        <aside className="w-full max-w-md p-6 border-r overflow-y-auto bg-white shadow-lg space-y-6">
          {/* Date picker */}
          <div>
            <label className="block text-sm font-medium mb-1">Select date</label>
            <Input
              type="date"
              value={day}
              onChange={handleDateChange}
              className="w-full px-3 py-2 border rounded-md text-sm"
            />
          </div>

          {/* Tag filters */}
          <div>
            <h2 className="text-sm font-medium mb-2">Filter by tag</h2>
            <div className="flex flex-wrap gap-2">
              {tagOptions.map((tag) => (
                <button
                  key={tag}
                  onClick={() => setActiveTag(tag)}
                  className={`px-3 py-1 rounded-full text-sm border focus:outline-none ${
                    activeTag === tag
                      ? "bg-blue-600 text-white border-blue-600"
                      : "text-gray-600 bg-gray-100 border-gray-300 hover:bg-gray-200"
                  }`}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>

          {/* Summary */}
          <SummaryPanel summary={data.summary} />
        </aside>

        {/* ───────── Timeline column ─────────────────────────────────────── */}
        <main className="flex-1 p-6 overflow-y-auto">
          <Card>
            <h1 className="text-2xl font-bold text-gray-800 text-center">
              LifeLog Viewer
            </h1>
            <div>
              <label className="block text-sm font-medium mb-1">Pick a date</label>
              <Input
                type="date"
                value={day}
                onChange={(e) => navigate(`/day/${e.target.value}`)}
              />
            </div>
            <Button
              onClick={() => navigate(`/day/${day}`)}
              className="w-full mt-4"
            >
              View Day
            </Button>
          </Card>

          <Timeline
            entries={sortedEntries.map((entry) => ({
              ...entry,
              color:
                entry.tags?.includes("Work")
                  ? "bg-green-500"
                  : entry.tags?.includes("Break")
                  ? "bg-yellow-500"
                  : "bg-gray-300",
            }))}
          />
        </main>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Helper components                                                         */
/* ────────────────────────────────────────────────────────────────────────── */
function CenteredMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <p className="text-gray-500">{children}</p>
    </div>
  );
}

function EmptyState(props: {
  message: string;
  actionLabel: string;
  action: () => void;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white shadow rounded-xl p-8 space-y-6 text-center">
        <p className="text-gray-600">{props.message}</p>
        <button
          onClick={props.action}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          {props.actionLabel}
        </button>
      </div>
    </div>
  );
}
