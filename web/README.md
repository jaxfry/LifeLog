# LifeLog Web Dashboard

A modern, responsive web dashboard for the LifeLog personal data aggregation platform.

## Features

- **Timeline View**: Browse your AI-generated activity timeline with search and filtering
- **Daily Summaries**: Review daily activities with productivity scores and mood tracking
- **Analytics Dashboard**: Visualize your activity patterns with interactive charts
- **Settings**: Manage devices, system configuration, and monitor health status
- **Authentication**: Secure login with JWT token-based authentication

## Technology Stack

- **Framework**: React 18 with Vite
- **Styling**: TailwindCSS for modern, responsive design
- **State Management**: TanStack Query (React Query) for API state
- **Routing**: React Router v6
- **Charts**: Recharts for data visualization
- **Icons**: Lucide React
- **Date Handling**: date-fns
- **HTTP Client**: Axios

## Setup

### Prerequisites

- Node.js 18+ and npm
- LifeLog backend server running (see ../server/README.md)

### Installation

1. Install dependencies:
   ```bash
   npm install
   ```

2. Configure environment variables:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set:
   - `VITE_API_URL`: URL of your LifeLog backend (default: http://localhost:8000/api/v1)

3. Start the development server:
   ```bash
   npm run dev
   ```

4. Open your browser to http://localhost:5173

### Production Build

Build the application for production:

```bash
npm run build
```

The built files will be in the `dist/` directory. You can serve them with any static file server.

### Preview Production Build

To preview the production build locally:

```bash
npm run preview
```

## Default Credentials

Before you can log in, you need to create a user in the backend. Use the backend API to create a superuser:

```bash
# See server documentation for user creation
```

## Project Structure

```
web/
├── src/
│   ├── components/      # Reusable UI components
│   │   ├── Layout.jsx   # Main layout with sidebar
│   │   └── ProtectedRoute.jsx
│   ├── contexts/        # React contexts
│   │   └── AuthContext.jsx
│   ├── pages/          # Page components
│   │   ├── Login.jsx
│   │   ├── Timeline.jsx
│   │   ├── DailySummaries.jsx
│   │   ├── Analytics.jsx
│   │   └── Settings.jsx
│   ├── services/       # API services
│   │   └── api.js
│   ├── utils/          # Utility functions
│   │   └── dateUtils.js
│   ├── App.jsx         # Main app component
│   ├── main.jsx        # Entry point
│   └── index.css       # Global styles
├── public/             # Static assets
├── .env.example        # Environment variables template
└── package.json
```

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint

## Features in Detail

### Timeline View
- Chronological display of AI-generated activity summaries
- Search functionality to filter timeline entries
- Pagination for browsing historical data
- Real-time updates with refresh button

### Daily Summaries
- Calendar-style navigation through days
- Productivity scores and mood tracking
- Key activities list
- AI-generated daily summaries
- On-demand summary generation

### Analytics Dashboard
- Activity trends over time (bar charts)
- Session status distribution (pie charts)
- Customizable time ranges (7, 14, 30 days)
- Recent sessions table with detailed information

### Settings
- Device management (create, delete, rotate API keys)
- System configuration viewing
- Health monitoring with system status checks
- Clean tabbed interface

## Development

The dashboard uses modern React patterns:

- **React Router** for client-side routing
- **TanStack Query** for server state management with caching
- **Context API** for authentication state
- **Custom hooks** for reusable logic
- **Responsive design** that works on mobile, tablet, and desktop

## API Integration

The dashboard communicates with the LifeLog backend API. All API calls are authenticated using JWT tokens stored in localStorage.

API endpoints used:
- `/token` - Authentication
- `/timeline` - Timeline data
- `/sessions` - Session data
- `/events` - Event data
- `/devices` - Device management
- `/config` - System configuration
- `/health` - Health checks
- `/admin/generate-summary/{date}` - Daily summary generation

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)

## License

[Add your license here]
