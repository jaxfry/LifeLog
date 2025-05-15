import type { TimelineEntry } from "../types";

export default function Timeline({ entries }: { entries: TimelineEntry[] }) {
  let lastDate = "";

  return (
    <div className="space-y-6">
      {entries.map((e, idx) => {
        const d = new Date(e.start).toLocaleDateString();
        const showDate = d !== lastDate;
        lastDate = d;

        return (
          <div key={idx}>
            {showDate && (
              <h3 className="mb-2 mt-6 text-sm font-bold text-gray-500">{d}</h3>
            )}

            <div className="bg-white rounded-xl shadow p-4 border border-gray-100">
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


function formatTime(raw: string): string {
  try {
    const date = new Date(raw);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return raw;
  }
}
