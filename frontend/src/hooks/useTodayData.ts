import { useDayData } from './useDayData';
import { formatDate } from '@/lib/utils';

// Helper function to get today's date in YYYY-MM-DD format
function getTodayString(): string {
  return formatDate(new Date());
}

export function useTodayData() {
  const todayString = getTodayString();
  return useDayData(todayString);
}