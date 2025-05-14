import type { TimelineEntry } from "../types";

export default function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <div className="space-y-4">
      {entries.map((e, idx) => (
        <div key={idx} className="relative group bg-white rounded-xl shadow p-4 border border-gray-100">
          <div className="text-sm text-gray-400 mb-1">
            {formatTime(e.start)} – {formatTime(e.end)}
          </div>
          <div className="text-lg font-semibold text-gray-800">{e.label}</div>
          <div className="text-sm text-gray-600 mb-2 line-clamp-2 group-hover:line-clamp-none transition-all">
            {e.summary}
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-gray-500 italic">
            {Array.isArray(e.tags)
              ? e.tags.map((tag) => (
                  <span
                    key={tag}
                    className="bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full"
                  >
                    {tag}
                  </span>
                ))
              : null}
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
