# LifeLog

A personal life logging and timeline management system that ingests data from various sources to create a comprehensive view of your digital activities, projects, and daily life.

## Features

- **Activity Tracking**: Ingests data from ActivityWatch to track digital activities
- **Project Management**: Automatic project detection and categorization using AI
- **Timeline Generation**: Creates structured timelines from raw activity data
- **Web Dashboard**: Modern React-based frontend for viewing and managing your data
- **REST API**: Full-featured API for data access and management

## Architecture

- **Backend**: FastAPI (Python) with DuckDB database
- **Frontend**: React + TypeScript + Vite
- **AI Processing**: Google Gemini API for intelligent categorization
- **Data Sources**: ActivityWatch integration (extensible for other sources)

## Getting Started

### Prerequisites

- Python 3.8+
- Node.js 16+
- ActivityWatch (for activity tracking)

### Setup

1. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd LifeLog
   ```

2. Set up the backend:
   ```bash
   # Install Python dependencies
   pip install -r requirements.txt
   
   # Copy environment file and configure
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. Set up the frontend:
   ```bash
   cd frontend
   npm install
   ```

### Configuration

Create a `.env` file in the root directory based on `.env.example`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
VITE_API_BASE=http://localhost:8000
```

### Running the Application

1. Start the backend:
   ```bash
   python -m backend.app.main
   ```

2. Start the frontend (in a new terminal):
   ```bash
   cd frontend
   npm run dev
   ```

3. Access the application at `http://localhost:5173`

## Project Structure

```
LifeLog/
├── backend/              # FastAPI backend
│   ├── app/
│   │   ├── api_v1/      # API endpoints
│   │   ├── core/        # Core functionality (DB, settings)
│   │   ├── daemon/      # Background processing
│   │   ├── ingestion/   # Data ingestion modules
│   │   └── processing/  # Data processing and AI integration
├── frontend/            # React frontend
│   └── src/
├── tests/              # Test files
└── tools/              # Utility scripts
```

## API Documentation

Once the backend is running, visit `http://localhost:8000/docs` for interactive API documentation.

## Development

### Backend Development

The backend uses FastAPI with DuckDB for data storage. Key components:

- **Ingestion**: Pulls data from ActivityWatch and other sources
- **Processing**: Uses AI to categorize activities into projects
- **API**: RESTful endpoints for frontend integration

### Frontend Development

The frontend is built with React, TypeScript, and Tailwind CSS. Features include:

- Dashboard with daily summaries
- Timeline view of activities
- Project management
- Authentication system

### Database Schema

The application uses DuckDB with the following main tables:
- `events`: Raw activity events
- `timeline_entries`: Processed timeline data
- `projects`: Project definitions and AI embeddings
- `users`: User authentication

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Add your license here]

## Privacy

This application processes personal activity data locally. All data remains on your machine unless you explicitly configure external integrations.
