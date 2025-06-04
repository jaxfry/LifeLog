import type { TimelineEntry, DailySummary } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const USE_MOCK_DATA = false; // Set to false to use real API

export interface DayResponse {
  entries: TimelineEntry[];
  summary: DailySummary;
}

// Mock data for development and UI testing
const MOCK_DATA: Record<string, DayResponse> = {
  "2025-05-27": {
    entries: [
      {
        start: "2025-05-27T09:00:00",
        end: "2025-05-27T11:30:00",
        label: "Coding session working on LifeLog UI improvements",
        activity: "VS Code",
        summary: "Worked on refactoring UI components and fixing design token implementation",
        tags: ["coding", "frontend", "development"],
        notes: "Focused on improving the user experience and fixing bugs."
      },
      {
        start: "2025-05-27T11:45:00",
        end: "2025-05-27T12:30:00",
        label: "Team meeting via Slack",
        activity: "Slack",
        summary: "Discussed project roadmap and upcoming features for Q2",
        tags: ["meeting", "communication"],
        notes: "Key discussion points included feature prioritization and deadlines."
      },
      {
        start: "2025-05-27T13:30:00",
        end: "2025-05-27T15:45:00",
        label: "Documentation work in Notion",
        activity: "Notion",
        summary: "Updated project documentation with new design system guidelines",
        tags: ["documentation", "design"],
        notes: "Added detailed explanations for the new design tokens."
      },
      {
        start: "2025-05-27T16:00:00",
        end: "2025-05-27T17:30:00",
        label: "Video research on YouTube",
        activity: "YouTube",
        summary: "Watched tutorials on advanced CSS and design systems",
        tags: ["learning", "research"]
      },
      {
        start: "2025-05-27T18:00:00",
        end: "2025-05-27T19:00:00", 
        label: "Music break on Spotify",
        activity: "Spotify",
        summary: "Relaxation and focus music during evening work",
        tags: ["break", "music"]
      }
    ],
    summary: {
      day_summary: "The day was heavily focused on LifeLog development, with significant coding sessions throughout the morning, afternoon, and evening. These productive periods were interspersed with extended system idle times, indicating breaks or time away from the computer. Other activities included brief social interactions on Discord, some AI research, and creative image editing.",
      stats: {
        total_active_time_min: 480,
        focus_time_min: 362,
        number_blocks: 8,
        top_project: "LifeLog",
        top_activity: "VS Code"
      },
      version: 1
    }
  }
};

/** Fetch /api/day/{YYYY-MM-DD} */
export async function getDay(day: string): Promise<DayResponse> {
  try {
    if (USE_MOCK_DATA) {
      // Use mock data or generate dynamic mock data for dates not in our mock set
      if (MOCK_DATA[day]) {
        return new Promise(resolve => {
          setTimeout(() => resolve(MOCK_DATA[day]), 500); // Simulate API delay
        });
      } else {
        // Generate mock data for any date
        const mockData = generateMockData(day);
        return new Promise(resolve => {
          setTimeout(() => resolve(mockData), 500);
        });
      }
    }
    
    // Use real API
    const res = await fetch(`${BASE_URL}/api/day/${day}`);
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    return res.json();
  } catch (error) {
    console.error("Error fetching day data:", error);
    return generateMockData(day); // Fallback to generated data on error
  }
}

function generateMockData(day: string): DayResponse {
  // Generate random activities for any given day
  const activities = ["VS Code", "Slack", "Notion", "YouTube", "Spotify", "Figma"];
  const tags = ["coding", "meeting", "documentation", "research", "design", "break", "frontend"];
  
  const entries: TimelineEntry[] = [];
  let startHour = 9;
  
  // Generate 3-6 random entries
  for (let i = 0; i < Math.floor(Math.random() * 4) + 3; i++) {
    const activity = activities[Math.floor(Math.random() * activities.length)];
    const duration = Math.floor(Math.random() * 3) + 1; // 1-3 hours
    
    // Random tags
    const entryTags: string[] = [];
    const numTags = Math.floor(Math.random() * 3) + 1;
    for (let j = 0; j < numTags; j++) {
      const tag = tags[Math.floor(Math.random() * tags.length)];
      if (!entryTags.includes(tag)) {
        entryTags.push(tag);
      }
    }
    
    entries.push({
      start: `${day}T${String(startHour).padStart(2, '0')}:00:00`,
      end: `${day}T${String(startHour + duration).padStart(2, '0')}:00:00`,
      label: `${activity} work session`,
      activity,
      summary: `Generated mock activity for ${activity}`,
      tags: entryTags
    });
    
    startHour += duration + Math.floor(Math.random() * 2); // Add gap between activities
    if (startHour >= 19) break; // Stop at 7PM
  }
  
  return {
    entries,
    summary: {
      day_summary: `Mock data for ${day}: Various activities including coding, meetings, and research.`,
      stats: {
        total_active_time_min: 480,
        focus_time_min: 360,
        number_blocks: entries.length,
        top_project: "LifeLog",
        top_activity: "VS Code"
      },
      version: 1
    }
  };
}
