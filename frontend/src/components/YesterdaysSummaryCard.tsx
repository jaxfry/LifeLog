import React from 'react';
import { useDayData } from '../hooks/useDayData'; // Use the generic hook for a specific date
import SummaryCard from './SummaryCard';

interface YesterdaysSummaryCardProps {
  className?: string;
}

export default function YesterdaysSummaryCard({ className }: YesterdaysSummaryCardProps) {
  // Hardcoded date for testing: May 22nd, 2025
  const testDateString = '2025-05-22';
  const { data, loading, error, hasData } = useDayData(testDateString);

  const testDate = new Date('2025-05-22');

  return (
    <SummaryCard
      title="Yesterday's Summary (Test: 2025-05-22)"
      date={testDate}
      dayData={data}
      loading={loading}
      error={error}
      hasData={hasData}
      className={className}
    />
  );
}
