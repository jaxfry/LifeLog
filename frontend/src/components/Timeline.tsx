import { TimelineEntry } from "../types";

export default function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <div className="space-y-4">
      {entries.map((e, i) => (
        <div key={i} className="border-l-4 pl-4 ml-2">
          <div className="text-sm text-gray-400">{e.start} – {e.end}</div>
          <div className="font-medium">{e.label}</div>
          <div className="text-sm">{e.summary}</div>
          <div className="text-xs text-gray-500 italic">
            {e.tags.join(", ")} {e.project ? `• ${e.project}` : ""}
          </div>
        </div>
      ))}
    </div>
  );
}
