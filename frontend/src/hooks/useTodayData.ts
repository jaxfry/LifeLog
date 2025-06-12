import { useDayData } from './useDayData';

// Helper function to get today's date in YYYY-MM-DD format
function getTodayString(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function useTodayData() {
  const todayString = getTodayString();
  return useDayData(todayString);
}