import React from "react";
import { motion } from "framer-motion";
import { Clock } from "lucide-react";
import { formatDuration, formatTime } from "../shared/utils";
import ActivityIcon from "./ui/ActivityIcon";
import { getTagColors } from "../shared/tag-styles";
import { useReducedMotion } from "../hooks/useReducedMotion";
import type { TimelineEntry } from "../types";

interface SegmentHeaderProps {
  label: string;
  spring: any;
}

function SegmentHeader({ label, spring }: SegmentHeaderProps) {
  return (
    <motion.h2
      initial={{ opacity: 0, y: 20, scale: 0.98 }}
      whileInView={{ opacity: 1, y: 0, scale: 1 }}
      viewport={{ once: false, amount: 0.2 }}
      transition={{ ...spring, duration: 0.4 }}
      className="mb-10 ml-4 type-caption uppercase tracking-wider text-secondary"
    >
      {label}
    </motion.h2>
  );
}

interface TimelineCardProps {
  entry: TimelineEntry;
  spring: any;
  reduceMotion: boolean;
}

function TimelineCard({ entry, spring, reduceMotion }: TimelineCardProps) {
  const start = new Date(entry.start);
  const end = new Date(entry.end);
  const duration = formatDuration(start, end);
  const timeRange = `${formatTime(start)} - ${formatTime(end)}`;

  const primaryColor = entry.tags?.[0] ? getTagColors(entry.tags[0]).backgroundColor : "var(--accent-500)";

  return (
    <motion.article
      initial={{ opacity: 0, y: 20, scale: 0.98 }}
      whileInView={{ opacity: 1, y: 0, scale: 1 }}
      viewport={{ once: false, amount: 0.1 }}
      transition={{ ...spring, duration: 0.4 }}
      className="group relative mb-16 last:mb-0"
    >
      {/* Marker */}
      <span
        className="absolute -left-[1.05rem] top-4 flex h-6 w-6 items-center justify-center rounded-full ring-4 ring-bg-900 shadow-card transition-all duration-300 group-hover:shadow-accent-500/50"
        style={{ backgroundColor: primaryColor }}
      >
        <ActivityIcon activity={entry.activity} size="sm" className="text-inverse" />
      </span>

      {/* Card */}
      <motion.div
        whileHover={reduceMotion ? undefined : { scale: 1.02 }}
        transition={{ type: "spring", stiffness: 200, damping: 20 }}
        className="relative ml-8 border-card bg-secondary p-6 backdrop-blur-md shadow-card hover:shadow-card-hover transition-hover"
        style={{ backgroundImage: `linear-gradient(135deg, ${primaryColor}0D 0%, transparent 70%)` }}
        aria-label={`Activity: ${entry.activity}`}
      >
        <header className="flex items-center justify-between gap-4">
          <h3 className="type-h3 text-primary capitalize">{entry.activity}</h3>
          <time className="rounded-lg bg-tertiary px-3 py-1 font-mono text-sm font-medium text-accent-500">
            {duration}
          </time>
        </header>

        {(entry.summary || entry.label) && (
          <p className="mt-3 type-body text-primary">
            {entry.summary || entry.label}
          </p>
        )}

        {entry.notes && (
          <p className="mt-2 type-caption italic text-secondary">
            {entry.notes}
          </p>
        )}

        {entry.tags && entry.tags.length > 0 && (
          <ul className="mt-4 flex flex-wrap gap-2" role="list" aria-label="Activity tags">
            {entry.tags.map((tag) => {
              const tagColors = getTagColors(tag);
              return (
                <li key={tag}>
                  <span
                    className="px-3 py-1 text-xs rounded-lg font-medium"
                    style={{
                      backgroundColor: `${tagColors.backgroundColor}20`,
                      color: tagColors.backgroundColor,
                      border: `1px solid ${tagColors.backgroundColor}40`,
                    }}
                    role="tag"
                  >
                    {tag}
                  </span>
                </li>
              );
            })}
          </ul>
        )}

        <div className="mt-4 flex items-center font-mono text-sm text-secondary">
          <Clock className="mr-2 h-4 w-4 flex-shrink-0 opacity-80" />
          <time dateTime={start.toISOString()}>{timeRange}</time>
        </div>
      </motion.div>
    </motion.article>
  );
}

export default function Timeline({ entries, date }: { entries: TimelineEntry[]; date?: Date }) {
  const reduceMotion = useReducedMotion();
  const spring = { type: "spring", stiffness: 150, damping: 25, mass: 0.7 };
  
  // Format the date for the header
  const formattedDate = date ? 
    new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric' }).format(date) : 
    "Your Timeline";
  
  let lastPart: string | null = null;

  return (
    <main className="relative min-h-screen overflow-x-hidden pb-32 pt-20 bg-primary text-primary">
      {/* Background aurora - subtle star field effect */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-x-0 top-0 h-80 bg-[radial-gradient(circle_at_25%_0%,rgba(85,221,251,0.03)_0%,transparent_70%)]" />
        <div className="absolute inset-x-0 bottom-0 h-96 rotate-180 bg-[radial-gradient(circle_at_75%_100%,rgba(129,108,255,0.04)_0%,transparent_70%)]" />
        {/* Subtle star field */}
        <div className="absolute inset-0 opacity-[0.02] bg-[radial-gradient(circle_at_20%_80%,white_1px,transparent_1px),radial-gradient(circle_at_80%_20%,white_1px,transparent_1px),radial-gradient(circle_at_40%_40%,white_1px,transparent_1px)] bg-[length:100px_100px,200px_200px,150px_150px]" />
      </div>

      {/* Heading */}
      <header className="mx-auto mb-24 max-w-3xl text-center">
        <motion.h1
          initial={{ opacity: 0, y: -32 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...spring, delay: 0.1 }}
          className="type-h1 text-primary drop-shadow-lg"
        >
          {formattedDate}
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...spring, delay: 0.25 }}
          className="mt-5 type-body text-secondary"
        >
          Your life, visualized.
        </motion.p>
      </header>

      {/* Timeline */}
      <section className="relative mx-auto max-w-2xl pl-10">
        <span className="pointer-events-none absolute left-4 top-0 h-full w-px bg-gradient-to-b from-transparent via-accent-500/60 to-transparent animate-pulse" />

        {entries.map((entry, index) => {
          const part = entry.tags?.[0] || getTimeOfDay(new Date(entry.start));
          const isNewSegment = part && part !== lastPart;
          lastPart = part;
          
          return (
            <React.Fragment key={`${entry.start}-${index}`}>
              {isNewSegment && <SegmentHeader label={part} spring={spring} />}
              <TimelineCard 
                entry={entry}
                spring={spring}
                reduceMotion={reduceMotion}
              />
            </React.Fragment>
          );
        })}
      </section>
    </main>
  );
}

// Helper function to get time of day
function getTimeOfDay(date: Date): string {
  const hour = date.getHours();
  if (hour < 6) return "Night";
  if (hour < 12) return "Morning";
  if (hour < 18) return "Afternoon";
  return "Evening";
}
