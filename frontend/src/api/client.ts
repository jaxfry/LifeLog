import type {
  TimelineEntry,
  DayDataResponse,
  Project,
  Event,
  TokenResponse,
  User, // Assuming you might want to fetch user profile later
  ProjectSuggestion
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const TOKEN_KEY = "authToken";

// --- Token Management ---

/**
 * Stores the authentication token in local storage.
 * @param token - The authentication token to store.
 */
export function storeToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/**
 * Retrieves the authentication token from local storage.
 * @returns The authentication token, or null if it doesn't exist.
 */
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Removes the authentication token from local storage.
 */
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

/**
 * Logs a user in and stores the authentication token.
 * @param formData - The form data containing the user's credentials.
 * @returns A promise that resolves to the token response.
 */
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

/**
 * Logs the current user out by removing the authentication token.
 */
export function logout(): void {
  removeToken();
  // Optionally, notify backend about logout if there's an endpoint for it
}

// --- Project Endpoints ---

/**
 * Creates a new project.
 * @param projectData - The data for the new project.
 * @returns A promise that resolves to the created project.
 */
export async function createProject(projectData: { name: string }): Promise<Project> {
  return request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(projectData),
  });
}

/**
 * Retrieves a list of projects.
 * @param skip - The number of projects to skip for pagination.
 * @param limit - The maximum number of projects to return.
 * @returns A promise that resolves to a list of projects.
 */
export async function getProjects(skip: number = 0, limit: number = 100): Promise<Project[]> {
  // Assuming the backend returns a simple list for now.
  // If it's a PaginatedResponse, adjust the return type and parsing.
  return request<Project[]>(`/projects?skip=${skip}&limit=${limit}`);
}

/**
 * Retrieves a project by its ID.
 * @param projectId - The ID of the project to retrieve.
 * @returns A promise that resolves to the requested project.
 */
export async function getProjectById(projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}`);
}

/**
 * Updates an existing project.
 * @param projectId - The ID of the project to update.
 * @param projectData - The data to update the project with.
 * @returns A promise that resolves to the updated project.
 */
export async function updateProject(
  projectId: string,
  projectData: Partial<{ name: string }>
): Promise<Project> {
  return request<Project>(`/projects/${projectId}`, {
    method: "PUT",
    body: JSON.stringify(projectData),
  });
}

/**
 * Deletes a project.
 * @param projectId - The ID of the project to delete.
 * @returns A promise that resolves when the project has been deleted.
 */
export async function deleteProject(projectId: string): Promise<void> {
  return request<void>(`/projects/${projectId}`, { method: "DELETE" });
}

/**
 * Retrieves a list of project suggestions.
 * @param status - Optional status to filter suggestions by.
 * @returns A promise that resolves to a list of project suggestions.
 */
export async function getProjectSuggestions(status?: "pending" | "accepted" | "rejected"): Promise<ProjectSuggestion[]> {
  const params = new URLSearchParams();
  if (status) {
    params.append("status", status);
  }
  return request<ProjectSuggestion[]>(`/projects/suggestions/?${params.toString()}`);
}

/**
 * Accepts a project suggestion.
 * @param suggestionId - The ID of the suggestion to accept.
 * @returns A promise that resolves to the newly created project.
 */
export async function acceptProjectSuggestion(suggestionId: string): Promise<Project> {
  return request<Project>(`/projects/suggestions/${suggestionId}/accept`, {
    method: "POST",
  });
}

/**
 * Rejects a project suggestion.
 * @param suggestionId - The ID of the suggestion to reject.
 * @returns A promise that resolves when the suggestion has been rejected.
 */
export async function rejectProjectSuggestion(suggestionId: string): Promise<void> {
  return request<void>(`/projects/suggestions/${suggestionId}/reject`, {
    method: "POST",
  });
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

/**
 * Creates a new timeline entry.
 * @param entryData - The data for the new timeline entry.
 * @returns A promise that resolves to the created timeline entry.
 */
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

/**
 * Retrieves a list of timeline entries.
 * @param params - The query parameters for filtering and pagination.
 * @returns A promise that resolves to a list of timeline entries.
 */
export async function getTimelineEntries(params: GetTimelineEntriesParams = {}): Promise<TimelineEntry[]> {
  const queryParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) {
      queryParams.append(key, String(value));
    }
  });
  return request<TimelineEntry[]>(`/timeline?${queryParams.toString()}`);
}

/**
 * Retrieves a timeline entry by its ID.
 * @param entryId - The ID of the timeline entry to retrieve.
 * @returns A promise that resolves to the requested timeline entry.
 */
export async function getTimelineEntryById(entryId: string): Promise<TimelineEntry> {
  return request<TimelineEntry>(`/timeline/${entryId}`);
}

/**
 * Updates an existing timeline entry.
 * @param entryId - The ID of the timeline entry to update.
 * @param entryData - The data to update the timeline entry with.
 * @returns A promise that resolves to the updated timeline entry.
 */
export async function updateTimelineEntry(
  entryId: string,
  entryData: TimelineEntryUpdateData
): Promise<TimelineEntry> {
  return request<TimelineEntry>(`/timeline/${entryId}`, {
    method: "PUT",
    body: JSON.stringify(entryData),
  });
}

/**
 * Deletes a timeline entry.
 * @param entryId - The ID of the timeline entry to delete.
 * @returns A promise that resolves when the timeline entry has been deleted.
 */
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

/**
 * Retrieves a list of events.
 * @param params - The query parameters for filtering and pagination.
 * @returns A promise that resolves to a list of events.
 */
export async function getEvents(params: GetEventsParams = {}): Promise<Event[]> {
  const queryParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) {
      queryParams.append(key, String(value));
    }
  });
  return request<Event[]>(`/events?${queryParams.toString()}`);
}

/**
 * Retrieves an event by its ID.
 * @param eventId - The ID of the event to retrieve.
 * @returns A promise that resolves to the requested event.
 */
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

/**
 * Triggers a manual processing run on the backend.
 * @returns A promise that resolves to a confirmation message.
 */
export async function triggerProcessing(): Promise<{ message: string }> {
  return request<{ message: string }>("/system/process-now", {
    method: "POST",
  });
}

/**
 * Retrieves the current status of the system.
 * @returns A promise that resolves to the system status object.
 */
export async function getSystemStatus(): Promise<Record<string, any>> {
  return request<Record<string, any>>("/system/status");
}

// Optional: Fetch current user details if there's an endpoint like /users/me
/**
 * Retrieves the currently authenticated user.
 * @returns A promise that resolves to the current user.
 */
export async function getCurrentUser(): Promise<User> {
  return request<User>("/users/me"); // Assuming you have a /users/me endpoint
}