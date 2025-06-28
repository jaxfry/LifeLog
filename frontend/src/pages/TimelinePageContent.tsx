"use client";

import { useEffect, useState } from "react";
import { format, formatRelative } from "date-fns";
import { Clock } from "lucide-react";
import { fetchDayData } from "@/api/client";
import { TimelineSidebarCalendar } from "@/components/TimelineSidebarCalendar";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { useSidebarContext } from "@/context/SidebarContext";
import { TimelineEntry } from "@/types";
import { cn, formatDuration, getActivityMetadata } from "@/lib/utils";
import { useSidebar } from "@/components/ui/sidebar";
import { ActivityIcon } from "@/components/ActivityIcon";

// Group entries by day
function groupEntriesByDay(entries: TimelineEntry[]): Record<string, TimelineEntry[]> {
    return entries.reduce((acc, entry) => {
        const date = format(new Date(entry.start_time), 'yyyy-MM-dd');
        if (!acc[date]) {
            acc[date] = [];
        }
        acc[date].push(entry);
        return acc;
    }, {} as Record<string, TimelineEntry[]>);
}

// Format the date header
function formatDateHeader(dateStr: string): { main: string; sub: string } {
    const today = new Date();
    const date = new Date(dateStr);
    const adjustedDate = new Date(date.valueOf() + date.getTimezoneOffset() * 60 * 1000);
    const relative = formatRelative(adjustedDate, today).split(' at ')[0];
    const formatted = format(adjustedDate, 'EEEE, MMMM d');
    
    return {
        main: relative.charAt(0).toUpperCase() + relative.slice(1),
        sub: formatted
    };
}

export default function TimelinePageContent() {
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<number | null>(null);
  const [selectedDate, setSelectedDate] = useState<Date>(new Date());
  const { setSidebarFooter } = useSidebarContext();
  const { state: sidebarState } = useSidebar();

  useEffect(() => {
    if (sidebarState === "expanded") {
      setSidebarFooter(
        <TimelineSidebarCalendar
          date={selectedDate}
          onDateChange={setSelectedDate}
        />
      );
    } else {
      setSidebarFooter(null);
    }
    return () => {
      setSidebarFooter(null);
    };
  }, [selectedDate, setSidebarFooter, sidebarState]);

  useEffect(() => {
    if (!selectedDate) return;
    const dateStr = format(selectedDate, "yyyy-MM-dd");
    setLoading(true);
    fetchDayData(dateStr)
      .then((data) => {
        const sortedData = (data && Array.isArray(data.timeline_entries))
          ? data.timeline_entries.sort((a, b) =>
              new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
            )
          : [];
        setEntries(sortedData);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [selectedDate]);

  const groupedEntries = groupEntriesByDay(entries);

  if (loading) {
    return (
        <div className="flex flex-1 items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
            <p className="text-muted-foreground">Loading activities...</p>
          </div>
        </div>
    );
  }

  if (error) {
    return (
        <div className="flex flex-1 items-center justify-center">
          <div className="text-destructive text-center">
            <p className="text-lg font-semibold">Error loading timeline</p>
            <p className="text-sm mt-2">{error}</p>
          </div>
        </div>
    );
  }

  return (
      <div className="flex flex-1 flex-row gap-8 p-4 md:p-8 max-w-7xl mx-auto w-full">
        {/* Main Timeline Content */}
        <div className="flex-1 flex flex-col gap-6">
          {/* Header */}
          <div className="space-y-2">
            <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
              Activity Timeline
            </h1>
            <p className="text-muted-foreground">
              Track your daily activities and productivity patterns
            </p>
          </div>

          {/* Timeline */}
          {Object.keys(groupedEntries).length === 0 ? (
            <Card className="p-12">
              <div className="text-center text-muted-foreground">
                <Clock className="h-12 w-12 mx-auto mb-4 opacity-20" />
                <p className="text-lg">No activities recorded yet</p>
                <p className="text-sm mt-2">Your timeline will appear here once activities are tracked</p>
              </div>
            </Card>
          ) : (
            <div className="space-y-12">
              {Object.entries(groupedEntries).map(([date, dayEntries]) => {
                const dateInfo = formatDateHeader(date);
                return (
                  <div key={date} className="relative">
                    {/* Date Header */}
                    <div className="sticky top-0 z-20 -mx-4 px-4 py-3 bg-background/95 backdrop-blur-lg border-b">
                      <div className="flex items-baseline gap-3">
                        <h2 className="text-xl font-semibold">{dateInfo.main}</h2>
                        <span className="text-sm text-muted-foreground">{dateInfo.sub}</span>
                        <Badge variant="secondary" className="ml-auto">
                          {dayEntries.length} activities
                        </Badge>
                      </div>
                    </div>

                    {/* Timeline Items */}
                    <div className="relative mt-8">
                      {/* Vertical Line */}
                      <div className="absolute left-8 top-0 bottom-0 w-0.5 bg-gradient-to-b from-border via-border/50 to-transparent"></div>
                      {dayEntries.map((entry, idx) => {
                        const metadata = getActivityMetadata(entry.title);
                        const startTime = new Date(entry.start_time);
                        const endTime = new Date(entry.end_time);
                        const duration = formatDuration(startTime, endTime);
                        const isSelected = selectedEntry === idx;
                        return (
                          <div
                            key={idx}
                            className={cn(
                              "relative mb-8 transition-all duration-300",
                              isSelected && "scale-[1.02]"
                            )}
                            onMouseEnter={() => setSelectedEntry(idx)}
                            onMouseLeave={() => setSelectedEntry(null)}
                          >
                            {/* Timeline Node */}
                            <div className={cn("absolute left-4 top-6 z-10 flex h-8 w-8 items-center justify-center rounded-full", metadata.bgClass)}>
                              <ActivityIcon icon={metadata.icon} className="h-5 w-5" />
                            </div>
                            <Card className={cn("ml-16 transform-gpu transition-all duration-300", isSelected ? "border-primary shadow-lg" : "hover:border-primary/50")}>
                              <CardHeader>
                                <div className="flex items-start justify-between gap-4">
                                  <div className="flex-1 space-y-1">
                                    <h3 className="font-semibold text-lg leading-tight">
                                      {entry.title}
                                    </h3>
                                    <p className="text-sm text-muted-foreground">
                                      {entry.summary || "No summary available"}
                                    </p>
                                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                      <div className="flex items-center gap-1">
                                        <Clock className="h-3 w-3" />
                                        <span>{format(startTime, 'h:mm a')} - {format(endTime, 'h:mm a')}</span>
                                      </div>
                                      <Badge
                                        variant="outline"
                                        className="text-xs"
                                      >
                                        {duration}
                                      </Badge>
                                    </div>
                                  </div>
                                  <Badge
                                    variant="outline"
                                    className={cn(
                                      "shrink-0",
                                      metadata.textClass,
                                      metadata.borderClass
                                    )}
                                  >
                                    {entry.project?.name || "No Project"}
                                  </Badge>
                                </div>
                              </CardHeader>
                              {/* entry.notes removed: not present in TimelineEntry */}
                            </Card>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
  );
}
