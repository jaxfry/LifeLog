// filepath: /Users/jaxon/Coding/LifeLog/frontend/src/components/TodaysSummaryCard.tsx
import React from 'react';
import { useTodayData } from '../hooks/useTodayData'; // Corrected import path
import SummaryCard from './SummaryCard';

interface TodaysSummaryCardProps {
  className?: string;
}

// Helper function to get a greeting based on current time
function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) return "Good night"; // Early morning, still night for some
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  if (hour < 22) return "Good evening";
  return "Good night"; // Late night
}

export default function TodaysSummaryCard({ className }: TodaysSummaryCardProps) {
  const { data, loading, error, hasData } = useTodayData();
  const today = new Date();

  return (
    <SummaryCard
      title="Today's Summary"
      date={today}
      dayData={data}
      loading={loading}
      error={error}
      hasData={hasData}
      className={className}
      greeting={getGreeting()} // Pass the greeting for today's card
    />
  );
}
