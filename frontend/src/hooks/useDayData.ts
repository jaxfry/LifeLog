import { useEffect, useState } from "react";
import * as apiClient from "@/api/client"; // Updated import
import type { DayDataResponse } from "@/types"; // Updated import
import { useAuth } from "@/context/AuthContext"; // To handle potential auth errors

/**
 * Custom hook to fetch and manage data for a specific day.
 *
 * @param dateString - The date string in 'YYYY-MM-DD' format.
 * @returns An object containing the day's data, loading state, error state, and a boolean indicating if data exists.
 */
export function useDayData(dateString: string | null) {
  const [data, setData] = useState<DayDataResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasData, setHasData] = useState(false);
  const { isAuthenticated } = useAuth(); // Get auth state

  useEffect(() => {
    let isMounted = true; // Track if the component is mounted

    if (!dateString) {
      setLoading(false);
      setError("No date provided.");
      setData(null);
      setHasData(false);
      return;
    }

    if (!isAuthenticated) {
      setLoading(false);
      setData(null);
      setHasData(false);
      return;
    }

    const fetchDataForDay = async () => {
      setLoading(true);
      setError(null);
      setData(null);
      setHasData(false);
      try {
        const dayData = await apiClient.fetchDayData(dateString);
        if (isMounted) {
          setData(dayData);
          setHasData(!!(dayData && (dayData.timeline_entries?.length > 0 || dayData.stats)));
        }
      } catch (err) {
        console.error("useDayData fetch error:", err);
        if (isMounted) {
          setError(err instanceof Error ? err.message : `Failed to fetch data for ${dateString}`);
          setData(null);
          setHasData(false);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchDataForDay();

    return () => {
      isMounted = false; // Set to false when the component unmounts or effect re-runs
    };
  }, [dateString, isAuthenticated]);

  return { data, loading, error, hasData };
}
