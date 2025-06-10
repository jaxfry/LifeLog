import { useEffect, useState } from "react";
import { getDay } from "../lib/api/client";
import type { DayResponse } from "../lib/api/client";

export function useDayData(day: string) {
  const [data, setData] = useState<DayResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getDay(day)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [day]);

  return { data, loading, error };
}
