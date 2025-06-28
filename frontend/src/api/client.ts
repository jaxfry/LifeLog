import type {
  TimelineEntry,
  DayDataResponse,
  Project,
  Event,
  TokenResponse,
  User // Assuming you might want to fetch user profile later
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const TOKEN_KEY = "authToken";

// --- Token Management ---

export function storeToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// --- API Request Helper ---

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers || {});
  headers.append("Content-Type", "application/json");

  if (token) {
    headers.append("Authorization", `Bearer ${token}`);
  }

  const config: RequestInit = {
    ...options,
    headers,
  };

  const response = await fetch(`${API_BASE_URL}${endpoint}`, config);

  if (!response.ok) {
    let errorMessage = `API request failed with status ${response.status}`;
    try {
      const errorBody = await response.json();
      errorMessage = errorBody.detail || errorMessage;
      if (Array.isArray(errorBody.detail)) {
        errorMessage = errorBody.detail.map((d: { msg: string; }) => d.msg).join(', ');
      }
    } catch (e) {
      // Ignore if error body is not JSON
    }
    if (response.status === 401) {
      // Potentially redirect to login or emit an event
      removeToken(); // Clear invalid token
      console.error("Authentication error: Token might be invalid or expired.");
    }
    throw new Error(errorMessage);
  }

  if (response.status === 204) { // No Content
    return undefined as T; // Or handle as appropriate for your app
  }
  return response.json();
}

// --- Authentication Endpoints ---

export async function login(
  formData: URLSearchParams // FastAPI's OAuth2PasswordRequestForm expects form data
): Promise<TokenResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(errorData.detail || `Login failed with status ${response.status}`);
  }
  const tokenResponse: TokenResponse = await response.json();
  storeToken(tokenResponse.access_token);
  return tokenResponse;
}

export function logout(): void {
  removeToken();
  // Optionally, notify backend about logout if there's an endpoint for it
}

// --- Project Endpoints ---

export async function createProject(projectData: { name: string }): Promise<Project> {
  return request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(projectData),
  });
}

export async function getProjects(skip: number = 0, limit: number = 100): Promise<Project[]> {
  // Assuming the backend returns a simple list for now.
  // If it's a PaginatedResponse, adjust the return type and parsing.
  return request<Project[]>(`/projects?skip=${skip}&limit=${limit}`);
}

export async function getProjectById(projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}`);
}

export async function updateProject(
  projectId: string,
  projectData: Partial<{ name: string }>
): Promise<Project> {
  return request<Project>(`/projects/${projectId}`, {
    method: "PUT",
    body: JSON.stringify(projectData),
  });
}

export async function deleteProject(projectId: string): Promise<void> {
  return request<void>(`/projects/${projectId}`, { method: "DELETE" });
}

// --- Timeline Entry Endpoints ---

export interface TimelineEntryCreateData {
  start_time: string;
  end_time: string;
  title: string;
  summary?: string | null;
  project_id?: string | null;
  source_event_ids?: string[] | null;
}

export interface TimelineEntryUpdateData {
  start_time?: string;
  end_time?: string;
  title?: string;
  summary?: string | null;
  project_id?: string | null;
  source_event_ids?: string[] | null;
}

export async function createTimelineEntry(entryData: TimelineEntryCreateData): Promise<TimelineEntry> {
  return request<TimelineEntry>("/timeline", {
    method: "POST",
    body: JSON.stringify(entryData),
  });
}

export interface GetTimelineEntriesParams {
  start_date?: string; // YYYY-MM-DD
  end_date?: string;   // YYYY-MM-DD
  project_id?: string;
  skip?: number;
  limit?: number;
  sort_by?: string;
  order?: "asc" | "desc";
}

export async function getTimelineEntries(params: GetTimelineEntriesParams = {}): Promise<TimelineEntry[]> {
  const queryParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) {
      queryParams.append(key, String(value));
    }
  });
  return request<TimelineEntry[]>(`/timeline?${queryParams.toString()}`);
}

export async function getTimelineEntryById(entryId: string): Promise<TimelineEntry> {
  return request<TimelineEntry>(`/timeline/${entryId}`);
}

export async function updateTimelineEntry(
  entryId: string,
  entryData: TimelineEntryUpdateData
): Promise<TimelineEntry> {
  return request<TimelineEntry>(`/timeline/${entryId}`, {
    method: "PUT",
    body: JSON.stringify(entryData),
  });
}

export async function deleteTimelineEntry(entryId: string): Promise<void> {
  return request<void>(`/timeline/${entryId}`, { method: "DELETE" });
}

// --- Event Endpoints ---
export interface GetEventsParams {
  start_time?: string; // ISO 8601
  end_time?: string;   // ISO 8601
  source?: string;
  event_type?: string;
  skip?: number;
  limit?: number;
}

export async function getEvents(params: GetEventsParams = {}): Promise<Event[]> {
  const queryParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) {
      queryParams.append(key, String(value));
    }
  });
  return request<Event[]>(`/events?${queryParams.toString()}`);
}

export async function getEventById(eventId: string): Promise<Event> {
  return request<Event>(`/events/${eventId}`);
}

// --- Day Data Endpoint (Updated) ---

/**
 * Fetches timeline entries and summary for a specific day.
 * @param day - Date string in YYYY-MM-DD format.
 */
export async function fetchDayData(day: string): Promise<DayDataResponse> {
  return request<DayDataResponse>(`/day/${day}`);
}

// --- System Endpoints ---

export async function triggerProcessing(): Promise<{ message: string }> {
  return request<{ message: string }>("/system/process-now", {
    method: "POST",
  });
}

export async function getSystemStatus(): Promise<Record<string, any>> {
  return request<Record<string, any>>("/system/status");
}

// Optional: Fetch current user details if there's an endpoint like /users/me
export async function getCurrentUser(): Promise<User> {
  return request<User>("/users/me"); // Assuming you have a /users/me endpoint
}