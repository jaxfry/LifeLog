import type { TimelineEntry } from "../types";

/**
 * Formats an ISO-8601 string or epoch-ms number into local HH:MM AM/PM.
 */
function formatTime(raw: string | number): string {
  const d = typeof raw === "number" ? new Date(raw) : new Date(raw);
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

function getColorByActivity(activity: string): string {
  const activityColors: Record<string, string> = {
    Work: "bg-blue-100 text-blue-800",
    Exercise: "bg-green-100 text-green-800",
    Leisure: "bg-purple-100 text-purple-800",
    Other: "bg-gray-100 text-gray-800",
  };
  return activityColors[activity] || "bg-gray-100 text-gray-800";
}

export default function Timeline({ entries }: { entries: TimelineEntry[] }) {
  let lastDate = "";

  return (
    <div className="space-y-6">
      {entries.map((e, idx) => {
        // Render local date heading, e.g. "May 13, 2025"
        const dateStr = new Date(e.start).toLocaleDateString(undefined, {
          year: "numeric",
          month: "long",
          day: "numeric",
        });
        const showDate = dateStr !== lastDate;
        lastDate = dateStr;

        return (
          <div key={idx}>
            {showDate && (
              <h3 className="mb-2 mt-6 text-sm font-bold text-gray-500">
                {dateStr}
              </h3>
            )}

            <div
              className={`bg-white rounded-xl shadow p-4 border border-gray-100 ${getColorByActivity(
                e.activity
              )}`}
            >
              <div className="text-xs text-gray-400 mb-1">
                {formatTime(e.start)} – {formatTime(e.end)}
              </div>
              <div className="text-lg font-semibold text-gray-800">
                {e.activity || e.label || "Untitled"}
              </div>
              {e.summary && (
                <div className="text-sm text-gray-600 mb-2 line-clamp-3">
                  {e.summary}
                </div>
              )}
              <div className="flex flex-wrap gap-2 text-xs text-gray-500 italic">
                {Array.isArray(e.tags) &&
                  e.tags.map((tag) => (
                    <span
                      key={tag}
                      className="bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full"
                    >
                      {tag}
                    </span>
                  ))}
                {e.project && (
                  <span className="ml-auto text-gray-400">• {e.project}</span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
