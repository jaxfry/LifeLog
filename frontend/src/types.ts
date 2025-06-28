/*  frontend/src/types.ts  */

/**
 * Represents a Project, aligning with backend `schemas.Project`.
 */
export interface Project {
  id: string; // UUID
  name: string;
}

/**
 * Represents a Timeline Entry, aligning with backend `schemas.TimelineEntry`.
 * Timestamps are expected to be ISO 8601 strings.
 */
export interface TimelineEntry {
  id: string; // UUID
  start_time: string; // ISO datetime string
  end_time: string;   // ISO datetime string
  title: string;
  summary?: string | null;
  project_id?: string | null; // UUID
  project?: Project | null;   // Populated project details
  local_day: string; // ISO date string (YYYY-MM-DD)
  // source_event_ids might be part of create/update but not typically in fetched list object
}

/**
 * Represents statistics for a day, aligning with backend `schemas.DayStats`.
 */
export interface DayStats {
  total_events: number;
  total_duration_hours: number;
  top_project: string | null;
  active_time_hours: number;
  break_time_hours: number;
}

/**
 * Represents a daily summary, aligning with backend `schemas.DailySummary`.
 */
export interface DailySummary {
  date: string; // ISO date string
  summary: string;
  insights: string[] | null;
}

/**
 * Represents the response for fetching data for a specific day,
 * aligning with backend `schemas.DayDataResponse`.
 */
export interface DayDataResponse {
  date: string; // ISO date string
  timeline_entries: TimelineEntry[];
  stats: DayStats;
  summary: DailySummary | null;
}

/**
 * Represents an Event, aligning with backend `schemas.Event`.
 */
export interface Event {
  id: string; // UUID
  source: string;
  event_type: string;
  start_time: string; // ISO datetime string
  end_time?: string | null; // ISO datetime string
  payload: Record<string, any>; // Generic dictionary for payload
  local_day: string; // ISO date string (YYYY-MM-DD)
}

/**
 * Represents user information, aligning with backend `schemas.User`.
 * This is typically received after authentication.
 */
export interface User {
  id: string; // UUID
  username: string;
  // email?: string | null; // If email is part of your User schema
  // is_active?: boolean; // If you have an active status
}

/**
 * Represents the token response from the authentication endpoint,
 * aligning with backend `schemas.Token`.
 */
export interface TokenResponse {
  access_token: string;
  token_type: string; // e.g., "bearer"
}

// Generic type for paginated responses if you implement pagination widely
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages?: number; // Optional: if your backend provides total pages
}