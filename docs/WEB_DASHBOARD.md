# LifeLog Web Dashboard

The LifeLog Web Dashboard is a modern, responsive web application built with React that provides a user-friendly interface for viewing and managing your personal data aggregation and insights.

## Overview

The dashboard provides four main sections:

1. **Timeline** - Browse your AI-generated activity timeline
2. **Daily Summaries** - Review daily activities and insights
3. **Analytics** - Visualize activity patterns and trends
4. **Settings** - Manage devices, configuration, and system health

## Features

### Authentication
- Secure login using JWT tokens
- OAuth2 password flow
- Automatic token refresh
- Session persistence with localStorage

### Timeline View
- Chronological display of AI-generated activity summaries
- Real-time search filtering across all timeline entries
- Pagination for browsing historical data
- Refresh functionality to fetch latest updates
- Relative time display (e.g., "2 hours ago")
- Detailed timestamp information
- Empty state handling with helpful messages

### Daily Summaries
- Interactive date navigation (previous/next day)
- Calendar-style date display
- Productivity scoring (0-10 scale)
- Mood tracking with emoji indicators
- Key activities list
- AI-generated narrative summaries
- On-demand summary generation for any date
- Summary regeneration capability

### Analytics Dashboard
- Real-time statistics cards:
  - Total sessions count
  - Total events count
  - Average sessions per day
  - Configurable time ranges (7, 14, 30 days)
- Interactive charts:
  - Sessions over time (bar chart)
  - Session status distribution (pie chart)
- Recent sessions table with:
  - Start time
  - Status indicators
  - Event counts
- Responsive chart sizing

### Settings
- **Devices Tab**:
  - View all registered devices
  - Add new devices with name and type
  - Delete devices
  - Rotate API keys for security
  - View last sync times
  - Copy device IDs
  
- **Configuration Tab**:
  - View system configuration
  - Configuration key-value pairs
  - Descriptions for each setting
  
- **System Health Tab**:
  - System status monitoring
  - Version information
  - Health check timestamps
  - Detailed health data in JSON format
  - Manual refresh capability

## Technology Stack

### Frontend Framework
- **React 18**: Modern React with hooks and functional components
- **Vite**: Fast build tool and dev server
- **React Router v6**: Client-side routing

### UI & Styling
- **TailwindCSS v3**: Utility-first CSS framework
- **Lucide React**: Beautiful, consistent icon set
- **Custom Components**: Reusable UI components

### State Management
- **TanStack Query (React Query)**: Server state management
  - Automatic caching
  - Background refetching
  - Optimistic updates
  - Request deduplication
- **React Context**: Authentication state

### Data Visualization
- **Recharts**: Composable charting library
  - Bar charts for time series
  - Pie charts for distributions
  - Responsive containers

### HTTP & API
- **Axios**: HTTP client with interceptors
  - Automatic auth token injection
  - Error handling
  - Request/response transformation

### Utilities
- **date-fns**: Modern date manipulation
  - Formatting
  - Relative time
  - Date arithmetic

## Architecture

### Component Structure

```
src/
├── components/
│   ├── Layout.jsx              # Main application layout
│   └── ProtectedRoute.jsx      # Route authentication wrapper
├── contexts/
│   └── AuthContext.jsx         # Authentication context provider
├── pages/
│   ├── Login.jsx               # Login page
│   ├── Timeline.jsx            # Timeline view
│   ├── DailySummaries.jsx      # Daily summaries view
│   ├── Analytics.jsx           # Analytics dashboard
│   └── Settings.jsx            # Settings page
├── services/
│   └── api.js                  # API client and endpoints
├── utils/
│   └── dateUtils.js            # Date formatting utilities
├── App.jsx                     # Root component with routing
├── main.jsx                    # Application entry point
└── index.css                   # Global styles and Tailwind
```

### Routing

The application uses client-side routing with the following routes:

- `/login` - Public login page
- `/` - Timeline view (protected)
- `/summaries` - Daily summaries (protected)
- `/analytics` - Analytics dashboard (protected)
- `/settings` - Settings page (protected)

All routes except `/login` require authentication.

### API Integration

The dashboard communicates with the LifeLog backend API at the URL specified in `VITE_API_URL` (default: http://localhost:8000/api/v1).

#### Authentication Flow
1. User enters credentials on login page
2. Frontend sends OAuth2 password flow request to `/token`
3. Backend validates credentials and returns JWT token
4. Frontend stores token in localStorage
5. All subsequent requests include token in Authorization header
6. On 401 response, user is redirected to login

#### API Endpoints Used

**Authentication**
- `POST /token` - Login and get access token

**Data Retrieval**
- `GET /timeline` - Fetch timeline entries
- `GET /sessions` - Fetch session data
- `GET /events` - Fetch event data
- `GET /logs` - Fetch raw logs

**Admin Operations**
- `GET /devices` - List registered devices
- `POST /devices` - Register new device
- `DELETE /devices/{id}` - Delete device
- `POST /devices/{id}/rotate-key` - Rotate API key
- `GET /config` - Get system configuration
- `PUT /config/{key}` - Update configuration
- `POST /admin/generate-summary/{date}` - Generate daily summary

**Health & Monitoring**
- `GET /health` - Get health status
- `GET /ready` - Get readiness status

### State Management

#### React Query Configuration
```javascript
{
  refetchOnWindowFocus: false,  // Don't refetch on window focus
  retry: 1,                      // Retry failed requests once
  staleTime: 30000              // Data is fresh for 30 seconds
}
```

#### Cache Keys
- `['timeline', page, limit]` - Timeline data
- `['sessions', params]` - Session data
- `['events', params]` - Event data
- `['dailySummary', dateStr]` - Daily summary for specific date
- `['devices']` - Device list
- `['config']` - System configuration
- `['health']` - System health status

## Responsive Design

The dashboard is fully responsive and works across different screen sizes:

### Mobile (< 768px)
- Collapsible sidebar with overlay
- Stacked card layouts
- Touch-friendly buttons
- Simplified tables

### Tablet (768px - 1024px)
- Sidebar toggles
- 2-column grid layouts
- Optimized chart sizes

### Desktop (> 1024px)
- Full sidebar always visible
- Multi-column layouts
- Large chart displays
- Side-by-side content

## Customization

### Theme Customization
The dashboard uses TailwindCSS, making it easy to customize colors and styles. Edit `tailwind.config.js` to modify:
- Color palette
- Font families
- Spacing scale
- Border radius
- Shadows

### Component Customization
Custom CSS classes are defined in `src/index.css`:
- `.btn-primary` - Primary button style
- `.btn-secondary` - Secondary button style
- `.card` - Card container style
- `.input-field` - Form input style

### API URL Configuration
Set the backend API URL in `.env`:
```bash
VITE_API_URL=http://your-server:8000/api/v1
```

## Development

### Running Locally
```bash
cd web
npm install
npm run dev
```

### Building for Production
```bash
npm run build
```

The production build is optimized and minified in the `dist/` directory.

### Preview Production Build
```bash
npm run preview
```

### Linting
```bash
npm run lint
```

## Deployment

### Static Hosting
The built files in `dist/` can be deployed to any static hosting service:
- Netlify
- Vercel
- GitHub Pages
- AWS S3 + CloudFront
- Nginx
- Apache

### Docker Deployment
You can serve the built files with a simple Nginx container:

```dockerfile
FROM nginx:alpine
COPY dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Environment Variables for Production
Create a `.env.production` file:
```bash
VITE_API_URL=https://api.your-domain.com/api/v1
```

Build with production environment:
```bash
npm run build
```

## Security Considerations

### Authentication
- JWT tokens stored in localStorage
- Tokens automatically included in all API requests
- Automatic logout on token expiration
- No sensitive data in URL parameters

### CORS
Backend must allow requests from the dashboard origin:
```python
BACKEND_CORS_ORIGINS = "http://localhost:5173,https://your-dashboard.com"
```

### HTTPS
Always use HTTPS in production to protect:
- Login credentials
- JWT tokens
- Personal data

### Content Security Policy
Consider adding CSP headers to restrict resource loading.

## Troubleshooting

### Login Issues
- Verify backend is running and accessible
- Check `VITE_API_URL` in `.env`
- Verify CORS settings on backend
- Check browser console for errors

### API Connection Errors
- Confirm backend URL is correct
- Check network tab in developer tools
- Verify API endpoints are responding
- Check authentication token validity

### Build Errors
- Clear node_modules: `rm -rf node_modules && npm install`
- Clear Vite cache: `rm -rf node_modules/.vite`
- Check Node.js version (18+ required)

### Display Issues
- Clear browser cache
- Check browser console for errors
- Verify all dependencies are installed
- Try different browser

## Future Enhancements

Potential improvements for the dashboard:

1. **Real-time Updates**: WebSocket support for live data
2. **Data Export**: Download timeline/summaries as PDF/CSV
3. **Advanced Filtering**: Multi-criteria filtering with saved filters
4. **Custom Dashboards**: User-configurable dashboard layouts
5. **Themes**: Dark mode and custom theme support
6. **Notifications**: In-app notifications for events
7. **Mobile App**: React Native mobile companion
8. **Offline Support**: Service workers for offline access
9. **Collaboration**: Multi-user support with sharing
10. **Integrations**: Direct connections to data sources

## Contributing

When contributing to the web dashboard:

1. Follow existing code style
2. Use functional components and hooks
3. Keep components focused and reusable
4. Add proper error handling
5. Test on multiple browsers
6. Ensure responsive design
7. Update documentation

## Support

For issues or questions:
- Check the [main documentation](../README.md)
- Review [Architecture Guide](architecture.md)
- Open an issue on GitHub
