# LifeLog

A personal life logging and timeline management system that ingests data from various sources to create a comprehensive view of your digital activities, projects, and daily life.

## Features

- **Activity Tracking**: Ingests data from ActivityWatch to track digital activities
- **Project Management**: Automatic project detection and categorization using AI
- **Timeline Generation**: Creates structured timelines from raw activity data
- **Web Dashboard**: Modern React-based frontend for viewing and managing your data
- **REST API**: Full-featured API for data access and management

## Architecture

- **Central Server Components:**
    - **API Service**: Unified FastAPI service with authentication, data management, and analytics (Port 8000)
    - **Data Ingestion Service**: FastAPI service for receiving data from local daemons (Port 8001)
    - **Data Processing Service**: Python worker for consuming data from RabbitMQ and processing it
    - **Message Queue**: RabbitMQ for decoupling services
    - **Database**: PostgreSQL with pgvector for storing processed data and embeddings
- **Frontend**: React + TypeScript + Vite (Port 5173 in development, Port 80 in production)
- **AI Processing**: Google Gemini API for intelligent categorization
- **Data Sources**: Local daemons (e.g., ActivityWatch integration) pushing to Data Ingestion Service

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

### Running the Application (New Docker-based Setup)

The new central server architecture (ingestion, processing, RabbitMQ, PostgreSQL) is managed using Docker Compose.

1.  **Ensure Docker and Docker Compose are installed.**
2.  **Set up environment variables:**
    Copy `.env.example` to `.env` and fill in any necessary values, especially `GEMINI_API_KEY`.
    ```bash
    cp .env.example .env
    # Edit .env with your API keys and any other custom configurations
    ```
    *Note: Database and RabbitMQ connection details within Docker Compose are handled by service names and do not typically need to be set in `.env` for the services to connect to each other within the Docker network. The `.env` file is more for local development outside Docker or for variables like API keys.*

3.  **Build and run the services using Docker Compose:**
    From the project root directory:
    ```bash
    docker-compose up --build
    ```
    To run in detached mode:
    ```bash
    docker-compose up -d --build
    ```
    This will:
    *   Build the Docker images for the `api_service`, `ingestion_service`, and `processing_service`.
    *   Start containers for all services including `postgres` and `rabbitmq`.
    *   The `postgres` service will initialize the database schema using scripts from `./postgres/init/`.
    *   The **API Service** will be accessible at `http://localhost:8000` (API docs at `http://localhost:8000/api/v1/docs`).
    *   The **Ingestion Service** will be accessible at `http://localhost:8001`.
    *   The **Processing Service** will start consuming messages from RabbitMQ.
    *   The **Frontend** will be accessible at `http://localhost:5173`.
    *   RabbitMQ management UI will be available at `http://localhost:15672` (default credentials: user/password).

4.  **Access the application:**
    *   **Frontend**: `http://localhost:5173`
    *   **API Documentation**: `http://localhost:8000/api/v1/docs`
    *   **RabbitMQ Management**: `http://localhost:15672` (user/password)
    *   **Login credentials**: Use `admin/admin123` for development

5.  **Stopping the services:**
    ```bash
    docker-compose down
    ```
    To stop and remove volumes (e.g., to reset database):
    ```bash
    docker-compose down -v
    ```

### Running the Legacy Application (Manual Setup - Being Phased Out)

If you need to run the older backend and frontend manually:

1. Start the old backend:
   ```bash
   # Ensure you have the old dependencies installed (requirements.txt in root)
   # python -m backend.app.main # This might be commented out or removed from docker-compose.yml
   echo "The old backend service is being phased out. Refer to older README versions if needed."
   ```

2. Start the frontend (in a new terminal):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. Access the application at `http://localhost:5173`

## Development Setup

If you want to run individual services for development:

## Project Structure

```
LifeLog/
├── central_server/           # Central server components
│   ├── api_service/         # Main FastAPI service (authentication, data management)
│   ├── ingestion_service/   # FastAPI service for data ingestion
│   └── processing_service/  # Python worker for data processing
├── frontend/                # React frontend
│   └── src/
├── postgres/                # PostgreSQL configuration and init scripts
│   └── init/
├── tests/                   # Test files
├── tools/                   # Utility scripts
└── local_daemon/           # Local daemon for data collection
```

## API Documentation

- **Main API Service**: `http://localhost:8000/api/v1/docs` (Swagger UI)
- **Data Ingestion Service**: `http://localhost:8001/docs` (Swagger UI)
- **API v1 Endpoints**:
  - Authentication: `/api/v1/auth/`
  - Projects: `/api/v1/projects/`
  - Timeline: `/api/v1/timeline/`
  - Events: `/api/v1/events/`
  - Daily Data: `/api/v1/day/`
  - System: `/api/v1/system/`

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

### Database Schema (New Central Server)

The new central server uses **PostgreSQL**. The schema is defined in `postgres/init/02_schema.sql` and includes tables for:
- Events, timeline entries, projects, users, etc. (Refer to the schema file for details).
- It also uses the `pgvector` extension for similarity searches on embeddings.

### Database Schema (Old Backend)

The old backend application used DuckDB with tables like:
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
