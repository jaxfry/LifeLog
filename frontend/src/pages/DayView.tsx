import { useParams, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useDayData } from "../hooks/useDayData";
import SummaryPanel from "../components/SummaryPanel";
import Timeline from "../components/Timeline";

/* Tags you want to filter by – extend as needed */
const TAGS = ["All", "Work", "Entertainment", "Research", "Social", "Creative"];

export default function DayView() {
  /* --- routing + data ---------------------------------------------------- */
  const { day = "" } = useParams<{ day: string }>();
  const navigate = useNavigate();
  const { data, loading, error } = useDayData(day);

  /* --- UI state ---------------------------------------------------------- */
  const [activeTag, setActiveTag] = useState<string>("All");

  /* --- helpers ----------------------------------------------------------- */
  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    navigate(`/day/${e.target.value}`);
  };

  const filteredEntries =
    activeTag === "All"
      ? data?.entries || []
      : (data?.entries || []).filter((e) => e.tags?.includes(activeTag));

  /* --- loading / error / empty states ------------------------------------ */
  if (loading)
    return <div className="p-6 text-center text-gray-500">Loading…</div>;

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

  /* --- main layout ------------------------------------------------------- */
  return (
    <div className="h-screen w-full bg-gray-50 text-gray-900 overflow-hidden">
      <div className="flex h-full">
        {/* ───── Sidebar ─────────────────────────────────────────────── */}
        <aside className="w-full max-w-md p-6 border-r overflow-y-auto bg-white shadow-lg space-y-6">
          {/* Date picker */}
          <div>
            <label className="block text-sm font-medium mb-1">Select date</label>
            <input
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
              {TAGS.map((tag) => (
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

          {/* Summary card */}
          <SummaryPanel summary={data.summary} />
        </aside>

        {/* ───── Timeline column ─────────────────────────────────────── */}
        <main className="flex-1 p-6 overflow-y-auto">
          <Timeline entries={filteredEntries} />
        </main>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Small reusable empty/error component                                       */
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
