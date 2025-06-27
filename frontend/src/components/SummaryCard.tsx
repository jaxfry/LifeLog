import React from 'react';
import { Clock, Calendar, Target, TrendingUp, Activity, AlertTriangle, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { DayDataResponse } from '@/types'; // Corrected import path

interface SummaryCardProps {
  title: string;
  date: Date;
  dayData: DayDataResponse | null;
  loading: boolean;
  error: string | null;
  hasData: boolean;
  className?: string;
  greeting?: string; // Optional: for Today's card
}

// Helper function to format time in hours and minutes
function formatTime(minutes: number): string {
  if (minutes < 0) return '0m'; // Handle potential negative values if data is imperfect
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (remainingMinutes === 0) {
    return `${hours}h`;
  }
  return `${hours}h ${remainingMinutes}m`;
}

// Helper function to get an icon based on top activity
function getActivityIcon(activity: string): React.ReactNode {
  if (!activity) return <Activity className="w-4 h-4" />;
  const activityLower = activity.toLowerCase();
  
  if (activityLower.includes('code') || activityLower.includes('program') || activityLower.includes('develop')) {
    return <span className="text-lg">💻</span>;
  }
  if (activityLower.includes('meeting') || activityLower.includes('call')) {
    return <span className="text-lg">🎯</span>;
  }
  if (activityLower.includes('read') || activityLower.includes('research')) {
    return <span className="text-lg">📚</span>;
  }
  if (activityLower.includes('write') || activityLower.includes('document')) {
    return <span className="text-lg">✍️</span>;
  }
  if (activityLower.includes('design')) {
    return <span className="text-lg">🎨</span>;
  }
  if (activityLower.includes('break') || activityLower.includes('lunch')) {
    return <span className="text-lg">☕</span>;
  }
  
  return <Activity className="w-4 h-4" />;
}

export default function SummaryCard({
  title,
  date,
  dayData,
  loading,
  error,
  hasData,
  className,
  greeting
}: SummaryCardProps) {

  // Show loading state
  if (loading) {
    return (
      <Card className={`p-6 ${className || ''}`}>
        <div className="animate-pulse">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-gray-200 rounded-lg"></div>
            <div className="flex-1">
              <div className="h-5 bg-gray-200 rounded mb-2 w-3/4"></div>
              <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="h-16 bg-gray-200 rounded"></div>
            <div className="h-16 bg-gray-200 rounded"></div>
          </div>
          <div className="mt-4 h-10 bg-gray-200 rounded"></div>
        </div>
      </Card>
    );
  }

  // Show error state
  if (error) {
    return (
      <Card className={`p-6 border-red-200 dark:border-red-700 bg-red-50 dark:bg-red-900/30 ${className || ''}`}>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold text-red-700 dark:text-red-300">{title}</CardTitle>
          <CardDescription className="text-xs text-red-600 dark:text-red-400">
            {date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
          </CardDescription>
        </CardHeader>
        <CardContent className="text-center py-4">
          <div className="flex flex-col items-center text-red-500 dark:text-red-400">
            <AlertTriangle className="w-10 h-10 mb-2" />
            <p className="font-semibold">Error loading data</p>
            <p className="text-xs">{error}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Show "no data" state (when hasData is explicitly false after loading)
  if (!hasData) {
    return (
      <Card className={`p-6 ${className || ''}`}>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold text-gray-700 dark:text-gray-300">{title}</CardTitle>
          <CardDescription className="text-xs text-gray-500 dark:text-gray-400">
            {date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
          </CardDescription>
        </CardHeader>
        <CardContent className="text-center py-8">
          <div className="flex flex-col items-center text-gray-500 dark:text-gray-400">
            <Info className="w-10 h-10 mb-3" />
            <p className="font-medium">No Data Available</p>
            <p className="text-sm text-gray-500 dark:text-gray-400">No activities were recorded for this day.</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Main card content when data is available
  return (
    <Card className={`shadow-sm hover:shadow-md transition-shadow duration-200 ease-in-out ${className || ''}`}>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          {/* Icon based on top activity or a default calendar icon */} 
          <div className="p-2 bg-muted rounded-lg">
            {dayData?.summary?.stats?.top_activity ? getActivityIcon(dayData.summary.stats.top_activity) : <Calendar className="w-6 h-6 text-primary" />}
          </div>
          <div className="flex-1 group">
            <CardTitle className="text-lg font-semibold text-gray-800 dark:text-white group-hover:text-primary transition-colors">
              {greeting ? `${greeting}, ${title}` : title}
            </CardTitle>
            <CardDescription className="text-xs text-gray-500 dark:text-gray-400">
              {date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 mb-5">
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-primary" />
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Active Time</p>
              <p className="text-base font-semibold text-gray-700 dark:text-gray-200">{formatTime(dayData?.summary?.stats?.total_active_time_min ?? 0)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Target className="w-5 h-5 text-green-500" />
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Focus Time</p>
              <p className="text-base font-semibold text-gray-700 dark:text-gray-200">{formatTime(dayData?.summary?.stats?.focus_time_min ?? 0)}</p>
            </div>
          </div>
        </div>

        {dayData?.summary?.stats?.top_project && (
          <div className="mb-4 p-3 bg-muted/50 rounded-lg">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Top Project</p>
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-indigo-500" />
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate" title={dayData.summary.stats.top_project}>
                {dayData.summary.stats.top_project}
              </p>
            </div>
          </div>
        )}

        {dayData?.summary?.stats?.top_activity && (
           <div className="mb-1 p-3 bg-muted/50 rounded-lg">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Top Activity</p>
            <div className="flex items-center gap-2">
              {getActivityIcon(dayData.summary.stats.top_activity)} 
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate" title={dayData.summary.stats.top_activity}>
                {dayData.summary.stats.top_activity}
              </p>
            </div>
          </div>
        )}

        {/* Productivity Score Badge - This field (productivity_score) is not in the current API schema.
            Commenting out until API and types support it.
        {dayData?.summary?.productivity_score !== undefined && dayData.summary.productivity_score !== null && (
          <div className="mt-5 text-center">
            <Badge
              variant={dayData.summary.productivity_score >= 0.7 ? "default" : dayData.summary.productivity_score >= 0.4 ? "secondary" : "destructive"}
              className="px-3 py-1 text-sm font-medium shadow-sm"
            >
              Productivity: {Math.round(dayData.summary.productivity_score * 100)}%
            </Badge>
          </div>
        )}
        */}
      </CardContent>
    </Card>
  );
}
