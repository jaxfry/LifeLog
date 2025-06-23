import { useEffect, useState } from "react";
import * as apiClient from "@/api/client"; // Updated import
import type { DayDataResponse } from "@/types"; // Updated import
import { useAuth } from "@/context/AuthContext"; // To handle potential auth errors

export function useDayData(dateString: string | null) {
  const [data, setData] = useState<DayDataResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasData, setHasData] = useState(false);
  const { isAuthenticated } = useAuth(); // Get auth state

  useEffect(() => {
    if (!dateString) {
      setLoading(false);
      setError("No date provided.");
      setData(null);
      setHasData(false);
      return;
    }

    // Don't fetch if not authenticated and trying to load data for a specific day
    // (unless some day data is public, which is not the case here)
    if (!isAuthenticated) {
      setLoading(false);
      // setError("User not authenticated."); // Or let ProtectedRoute handle it
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
        const dayData = await apiClient.fetchDayData(dateString); // Use new client
        setData(dayData);
        // Ensure alignment with new TimelineEntry structure if needed for 'hasData' logic
        setHasData(!!(dayData && (dayData.entries?.length > 0 || dayData.summary?.stats)));
      } catch (err) {
        console.error("useDayData fetch error:", err);
        setError(err instanceof Error ? err.message : `Failed to fetch data for ${dateString}`);
        setData(null);
        setHasData(false);
        // If 401, AuthContext/ProtectedRoute should ideally handle redirection.
      } finally {
        setLoading(false);
      }
    };

    fetchDataForDay();
  }, [dateString, isAuthenticated]); // Re-run effect if dateString or auth status changes

  return { data, loading, error, hasData };
}
