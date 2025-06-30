import { useDayData } from './useDayData';
import { formatDate } from '@/lib/utils';

// Helper function to get yesterday's date in YYYY-MM-DD format
function getYesterdayString(): string {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  return formatDate(yesterday);
}

export function useYesterdayData() {
  const yesterdayString = getYesterdayString();
  return useDayData(yesterdayString);
}
