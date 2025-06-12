import { useEffect, useState } from "react";
import { fetchDayData } from "../api/client";
import type { DayDataResponse } from "../api/client";

export function useDayData(dateString: string | null) {
  const [data, setData] = useState<DayDataResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasData, setHasData] = useState(false);

  useEffect(() => {
    if (!dateString) {
      setLoading(false);
      setError("No date provided.");
      setData(null);
      setHasData(false);
      return;
    }

    const fetchDataForDay = async () => {
      try {
        setLoading(true);
        setError(null);
        setData(null);
        setHasData(false);
        const dayData = await fetchDayData(dateString);
        setData(dayData);
        setHasData(!!(dayData && (dayData.entries?.length > 0 || dayData.summary?.stats)));
      } catch (err) {
        setError(err instanceof Error ? err.message : `Failed to fetch data for ${dateString}`);
        setData(null);
        setHasData(false);
      } finally {
        setLoading(false);
      }
    };

    fetchDataForDay();
  }, [dateString]); // Re-run effect if dateString changes

  return { data, loading, error, hasData };
}
