import { useParams, useNavigate } from "react-router-dom";
import { useDayData } from "../hooks/useDayData";
import SummaryPanel from "../components/SummaryPanel";
import Timeline from "../components/Timeline";
import { useState } from "react";

const TAGS = ["All", "Work", "Entertainment", "Research", "Social", "Creative"];

export default function DayView() {
  const { day = "" } = useParams<{ day: string }>();
  const navigate = useNavigate();
  const { data, loading, error } = useDayData(day);
  const [activeTag, setActiveTag] = useState<string>("All");

  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    navigate(`/day/${e.target.value}`);
  };

  const filteredEntries =
    activeTag === "All"
      ? data?.entries || []
      : (data?.entries || []).filter((e) => e.tags?.includes(activeTag));

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <input
          type="date"
          value={day}
          onChange={handleDateChange}
          className="border rounded px-2 py-1 text-sm"
        />
        <div className="flex space-x-2">
          {TAGS.map((tag) => (
            <button
              key={tag}
              className={`px-3 py-1 rounded-full text-sm border ${
                activeTag === tag
                  ? "bg-blue-600 text-white"
                  : "bg-white text-gray-600 border-gray-300"
              }`}
              onClick={() => setActiveTag(tag)}
            >
              {tag}
            </button>
          ))}
        </div>
      </div>

      {loading && <div>Loading...</div>}
      {error && <div className="text-red-600">{error}</div>}
      {data && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-1">
            <SummaryPanel summary={data.summary} />
          </div>
          <div className="md:col-span-2">
            <Timeline entries={filteredEntries} />
          </div>
        </div>
      )}
    </div>
  );
}