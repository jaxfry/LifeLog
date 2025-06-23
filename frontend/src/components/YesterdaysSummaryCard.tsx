import React from 'react';
import { useYesterdayData } from '@/hooks/useYesterdayData'; // Updated to use specific hook and alias
import SummaryCard from './SummaryCard';

interface YesterdaysSummaryCardProps {
  className?: string;
}

// Helper function to get yesterday's date object
function getYesterdayDate(): Date {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  return yesterday;
}

export default function YesterdaysSummaryCard({ className }: YesterdaysSummaryCardProps) {
  const { data, loading, error, hasData } = useYesterdayData();
  const yesterdayDate = getYesterdayDate(); // Get yesterday's date for the title

  return (
    <SummaryCard
      title="Yesterday's Summary"
      date={yesterdayDate} // Pass the actual yesterday's date
      dayData={data}
      loading={loading}
      error={error}
      hasData={hasData}
      className={className}
    />
  );
}
