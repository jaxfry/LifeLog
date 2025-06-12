/*  frontend/src/types.ts  */
export interface TimelineEntry {
  start: string;
  end: string;
  label: string;
  activity: string;
  summary: string;
  tags: string[];
  project?: string | null;
  notes?: string; // Optional field for user-provided notes
}

export interface DailySummary {
  day_summary: string;
  stats: {
    total_active_time_min: number;
    focus_time_min: number;
    number_blocks: number;
    top_project: string;
    top_activity: string;
  };
  version: number;
}