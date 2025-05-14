import type { TimelineEntry } from "../types";

export default function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <div className="space-y-6">
      {entries.map((e, idx) => (
        <div key={idx} className="bg-white rounded-xl shadow p-4 border border-gray-100">
          {/* Time */}
          <div className="text-xs text-gray-400 mb-1">
            {formatTime(e.start)} – {formatTime(e.end)}
          </div>

          {/* Main activity */}
          <div className="text-lg font-semibold text-gray-800">
            {e.activity || e.label || "Untitled"}
          </div>

          {/* Summary (if available) */}
          {e.summary && (
            <div className="text-sm text-gray-600 mb-2 line-clamp-3 hover:line-clamp-none transition-all">
              {e.summary}
            </div>
          )}

          {/* Tags + Project */}
          <div className="flex flex-wrap gap-2 items-center text-xs text-gray-500 italic">
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
      ))}
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
