"use client";

import { useEffect, useState } from "react";
import DashboardLayout from "@/layouts/DashboardLayout";
import { fetchDayData } from "@/api/client";
import type { TimelineEntry } from "@/types";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Clock } from "lucide-react"; // Removed Calendar, MessageSquare, ChevronRight
import { format, formatRelative } from "date-fns";
import { getActivityMetadata, formatDuration } from "@/lib/timeline-utils";
import { cn } from "@/lib/utils";

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

export default function TimelinePage() {
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<number | null>(null);

  useEffect(() => {
    const date = "2025-05-22";
    fetchDayData(date)
      .then((data) => {
        const sortedData = data.entries.sort((a, b) => 
          new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
        );
        setEntries(sortedData);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const groupedEntries = groupEntriesByDay(entries);

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex flex-1 items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
            <p className="text-muted-foreground">Loading activities...</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout>
        <div className="flex flex-1 items-center justify-center">
          <div className="text-destructive text-center">
            <p className="text-lg font-semibold">Error loading timeline</p>
            <p className="text-sm mt-2">{error}</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="flex flex-1 flex-col gap-6 p-4 md:p-8 max-w-5xl mx-auto w-full">
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
                          <div className="absolute left-4 top-6 z-10">
                            <div className={cn(
                              "relative flex h-12 w-12 items-center justify-center rounded-full transition-all duration-300",
                              metadata.bgClass,
                              isSelected && "scale-110"
                            )}>
                              <div className={cn(
                                "flex h-8 w-8 items-center justify-center rounded-full transition-colors",
                                metadata.iconBgClass
                              )}>
                                <metadata.icon className={cn("h-4 w-4", metadata.textClass)} />
                              </div>
                              {/* Pulse animation for recent items */}
                              {idx === 0 && (
                                <div className={cn(
                                  "absolute inset-0 rounded-full animate-ping",
                                  metadata.bgClass,
                                  "opacity-20"
                                )} />
                              )}
                            </div>
                          </div>

                          {/* Content Card */}
                          <Card className={cn(
                            "ml-20 overflow-hidden transition-all duration-300 hover:shadow-lg",
                            "border-l-4",
                            metadata.borderClass,
                            isSelected && "shadow-lg"
                          )}>
                            <CardHeader className="pb-3">
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
    </DashboardLayout>
  );
}
