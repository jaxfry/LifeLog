# AI Chat Application Usage Tracking

## Overview

The AI chat system has been enhanced to properly track and report application usage time, particularly for media consumption activities like anime watching.

## Problem

Previously, the AI chatbot only had access to processed Timeline entries, which aggregate and summarize activities. This caused several issues:

1. **Loss of Detail**: Timeline entries are high-level summaries that might combine multiple applications or activities
2. **Inaccurate Time Tracking**: When users asked "How much anime have I watched?", the AI couldn't accurately calculate time spent in specific applications
3. **Missing Application Context**: The AI didn't have direct access to raw application usage data from ActivityWatch

### Example Issue

User query: "How much anime have I watched this month?"

**Before**: AI reported ~22 minutes based on YouTube video titles and browser activity  
**Actual**: User watched 7+ hours using the Hayase media player application

The problem was that Hayase usage was either:
- Summarized into generic timeline entries without application details
- Not properly recognized as anime watching activity

## Solution

### 1. Application Usage Statistics

Added a new function `get_app_usage_stats()` that:
- Queries raw `Event` records of type `app_usage`
- Aggregates total duration by application name
- Provides accurate time tracking for any application

```python
async def get_app_usage_stats(
    session: AsyncSession, 
    days: int = 7, 
    user_timezone: str = "UTC",
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> dict
```

### 2. Enhanced AI Context

The `get_user_context()` function now includes:
- Daily summaries (as before)
- Timeline entries (as before)
- **NEW**: Application Usage Statistics section

Example context provided to AI:
```
# Application Usage Statistics (Past 7 days)
- Hayase: 7.0 hours
- VS Code: 4.0 hours
- Chrome: 3.0 hours
- Terminal: 2.0 hours
```

### 3. Improved System Prompt

The AI chat system prompt now includes:

**Application Recognition Guidelines:**
- Explicit instructions to check Application Usage Statistics first
- Knowledge that "Hayase" is a media player for anime/videos
- Instructions to sum up relevant application usage
- Guidance to cite specific applications and durations

**Timeline Generation Improvements:**
- Added application recognition hints in the timeline enrichment prompt
- Specific guidance for categorizing media player applications (Hayase, VLC, mpv, etc.)
- Instructions to preserve application context in activity descriptions

## Benefits

1. **Accurate Time Tracking**: AI can now report exact durations from raw application usage data
2. **Better Context**: AI understands which applications are used for which activities
3. **Flexible Queries**: Users can ask about time spent in specific applications or activity types
4. **Improved Summaries**: Daily summaries can reference specific application usage

## Usage Examples

### Query: "How much anime have I watched this month?"

**AI Response (After Fix):**
```
Based on your application usage statistics for the past month, you've watched 
approximately 7 hours of anime using the Hayase media player. Additionally, 
there were about 20 minutes of anime-related content on YouTube...
```

### Query: "What did I do yesterday?"

**AI Response:**
```
Yesterday you spent:
- 4.5 hours coding in VS Code
- 2.0 hours in meetings (Chrome + Zoom)
- 1.5 hours watching anime (Hayase)
...
```

## Technical Details

### Data Flow

1. **Collection**: ActivityWatch collector tracks application usage
2. **Normalization**: Events processor creates `app_usage` events with app name and duration
3. **Storage**: Events stored in database with full detail
4. **Timeline**: AI generates high-level timeline entries (may aggregate)
5. **Chat Context**: AI chat queries both timeline entries AND raw event aggregations

### Database Schema

Events table structure (relevant fields):
- `type`: "app_usage" for application usage events
- `data.app`: Application name (e.g., "Hayase", "Chrome", "VS Code")
- `data.duration`: Duration in seconds (numeric: int or float). The aggregation function validates and converts to float, defaulting to 0 for invalid values.
- `data.title`: Window title (optional additional context)
- `created_at`: Timestamp of the event

### Performance Considerations

- Application usage stats are aggregated on-demand for chat queries
- Default lookback period is 7 days (configurable via `context_days` parameter)
- Query can be filtered by custom date range for specific time periods
- Only non-superseded events are included in aggregation

## Future Improvements

Potential enhancements:
1. **Application Categories**: Pre-define categories (media player, IDE, browser, etc.)
2. **Smart Time Filtering**: Better support for "this month", "last week" queries
3. **Per-Day Breakdown**: Show day-by-day application usage trends
4. **Application Aliases**: Map multiple names to same application (e.g., "Chrome" = "Google Chrome")
5. **Activity Correlation**: Link application usage with timeline activities more explicitly

## Configuration

No configuration changes required. The enhancement works automatically with existing:
- ActivityWatch integration
- Event processing pipeline
- AI chat endpoint

## Testing

Test coverage includes:
- Application usage aggregation logic
- Context generation with statistics
- Time formatting (hours vs minutes)
- Multi-day aggregation

See `/tmp/test_app_usage.py` and `/tmp/test_context_generation.py` for test examples.
