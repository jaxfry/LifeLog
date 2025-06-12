import { useDayData } from './useDayData';

// Helper function to get yesterday's date in YYYY-MM-DD format
function getYesterdayString(): string {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  return yesterday.getFullYear() + '-' +
    String(yesterday.getMonth() + 1).padStart(2, '0') + '-' +
    String(yesterday.getDate()).padStart(2, '0');
}

export function useYesterdayData() {
  const yesterdayString = getYesterdayString();
  return useDayData(yesterdayString);
}
