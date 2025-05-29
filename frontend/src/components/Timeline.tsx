import React from "react";
import { motion } from "framer-motion";
import { Clock } from "lucide-react";
import { formatDuration, formatTime } from "../lib/utils";
import ActivityIcon from "./ui/ActivityIcon";
import { getTagStyle } from "../lib/tag-styles";
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
      className="mb-10 ml-4 text-lg font-semibold uppercase tracking-wider text-gray-400"
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

  const primaryColor = entry.tags?.[0] ? getTagStyle(entry.tags[0]).backgroundColor : "#6366f1";

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
        className="absolute -left-[1.05rem] top-4 flex h-6 w-6 items-center justify-center rounded-full ring-4 ring-gray-950 shadow-[0_0_8px_0] shadow-transparent transition-all duration-300 group-hover:shadow-violet-500/50"
        style={{ backgroundColor: primaryColor }}
      >
        <ActivityIcon activity={entry.activity} size="sm" className="text-white" />
      </span>

      {/* Card */}
      <motion.div
        whileHover={reduceMotion ? undefined : { scale: 1.02, boxShadow: `0px 0px 20px 0px ${primaryColor}30` }}
        transition={{ type: "spring", stiffness: 200, damping: 20 }}
        className="relative ml-8 rounded-3xl bg-gray-900/70 p-6 backdrop-blur-md shadow-md shadow-black/40"
        style={{ backgroundImage: `linear-gradient(135deg, ${primaryColor}0D 0%, transparent 70%)` }}
        aria-label={`Activity: ${entry.activity}`}
      >
        <header className="flex items-center justify-between gap-4">
          <h3 className="text-xl font-semibold text-white capitalize">{entry.activity}</h3>
          <time className="rounded-full bg-gray-800/60 px-3 py-0.5 text-sm font-medium text-blue-200">
            {duration}
          </time>
        </header>

        {(entry.summary || entry.label) && (
          <p className="mt-2 text-base leading-relaxed text-gray-300">
            {entry.summary || entry.label}
          </p>
        )}

        {entry.notes && (
          <p className="mt-2 text-sm italic text-gray-400">
            {entry.notes}
          </p>
        )}

        {entry.tags && entry.tags.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-1" role="list" aria-label="Activity tags">
            {entry.tags.map((tag) => {
              const tagStyle = getTagStyle(tag);
              return (
                <li key={tag}>
                  <span
                    className="px-2 py-0.5 text-xs rounded-full"
                    style={{
                      backgroundColor: `${tagStyle.backgroundColor}33`,
                      color: tagStyle.backgroundColor,
                      border: `1px solid ${tagStyle.backgroundColor}44`,
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

        <div className="mt-4 flex items-center text-sm text-gray-400">
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
    <main className="relative min-h-screen overflow-x-hidden bg-gradient-to-b from-indigo-950 via-violet-950 to-amber-950 pb-32 pt-20 font-inter text-gray-100">
      {/* Background aurora */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-x-0 top-0 h-80 bg-[radial-gradient(circle_at_25%_0%,rgba(255,255,255,0.04)_0%,transparent_70%)]" />
        <div className="absolute inset-x-0 bottom-0 h-96 rotate-180 bg-[radial-gradient(circle_at_75%_100%,rgba(255,255,255,0.05)_0%,transparent_70%)]" />
      </div>

      {/* Heading */}
      <header className="mx-auto mb-24 max-w-3xl text-center">
        <motion.h1
          initial={{ opacity: 0, y: -32 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...spring, delay: 0.1 }}
          className="font-serif text-6xl font-extrabold tracking-tight text-white drop-shadow-lg"
        >
          {formattedDate}
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...spring, delay: 0.25 }}
          className="mt-5 text-lg text-gray-300"
        >
          Your day, retold—moments of focus, flow &amp; serendipity ✨
        </motion.p>
      </header>

      {/* Timeline */}
      <section className="relative mx-auto max-w-2xl pl-10">
        <span className="pointer-events-none absolute left-4 top-0 h-full w-px bg-gradient-to-b from-transparent via-violet-500/60 to-transparent animate-pulse" />

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
