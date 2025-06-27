# LifeLog

A personal life logging and timeline management system that ingests data from various sources to create a comprehensive view of your digital activities, projects, and daily life.

## Features

- **Activity Tracking**: Ingests data from ActivityWatch to track digital activities
- **Project Management**: Automatic project detection and categorization using AI
- **Timeline Generation**: Creates structured timelines from raw activity data
- **Web Dashboard**: Modern React-based frontend for viewing and managing your data
- **REST API**: Full-featured API for data access and management

## Architecture

- **Central Server Components (New):**
    - **Data Ingestion Service**: FastAPI (Python) - Receives data and queues it in RabbitMQ.
    - **Data Processing Service**: Python Worker - Consumes data from RabbitMQ, processes it, and stores it in PostgreSQL.
    - **Message Queue**: RabbitMQ - For decoupling services.
    - **Database**: PostgreSQL with pgvector - For storing processed data and embeddings.
- **Old Backend (Being Phased Out)**: FastAPI (Python) with DuckDB database
- **Frontend**: React + TypeScript + Vite
- **AI Processing**: Google Gemini API for intelligent categorization (used by Data Processing Service)
- **Data Sources**: Local daemons (e.g., ActivityWatch integration) pushing to Data Ingestion Service.

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
    *   Build the Docker images for the `ingestion_service` and `processing_service`.
    *   Start containers for `ingestion_service`, `processing_service`, `rabbitmq`, and `postgres`.
    *   The `postgres` service will initialize the database schema using scripts from `./postgres/init/`.
    *   The `ingestion_service` will be accessible (e.g., at `http://localhost:8001` by default, check `docker-compose.yml` for port mappings).
    *   The `processing_service` will start consuming messages from RabbitMQ.
    *   RabbitMQ management UI will be available at `http://localhost:15672` (default credentials: user/password).

4.  **Running the Frontend (Optional, if needed for testing with new backend):**
    If you want to run the existing frontend:
    ```bash
    cd frontend
    npm install # if you haven't already
    npm run dev
    ```
    Access the frontend at `http://localhost:5173`. You might need to update frontend API configurations to point to the new `ingestion_service` if it's handling direct client interactions, or adjust how data flows if the frontend is meant to read processed data. *(This part might need further refinement based on how the frontend interacts with the new backend pipeline).*

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

## Project Structure

```
LifeLog/
├── central_server/       # New central server components
│   ├── ingestion_service/  # FastAPI service for data ingestion
│   ├── processing_service/ # Python worker for data processing
├── backend/              # Old FastAPI backend (being phased out)
│   ├── app/
│   │   ├── api_v1/      # API endpoints
│   │   ├── core/        # Core functionality (DB, settings)
│   │   ├── daemon/      # Background processing
│   │   ├── ingestion/   # Data ingestion modules
│   │   └── processing/  # Data processing and AI integration
├── frontend/            # React frontend
│   └── src/
├── postgres/             # PostgreSQL configuration and init scripts
│   └── init/
├── tests/              # Test files
└── tools/              # Utility scripts
```

## API Documentation

- **New Data Ingestion Service**: If running via Docker Compose, API docs (Swagger UI) typically at `http://localhost:8001/docs` (check `docker-compose.yml` for port mapping).
- **Old Backend API**: If running, visit `http://localhost:8000/docs`.

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
