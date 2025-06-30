# LifeLog Project

LifeLog is a comprehensive personal data aggregation and analysis platform. It collects data from various sources, processes it, and provides insights through a web-based frontend.

## Project Architecture

The LifeLog project is built on a microservices architecture, consisting of the following components:

*   **Frontend:** A React-based single-page application that provides the user interface for visualizing and interacting with the collected data.
*   **API Service:** A FastAPI application that serves as the primary gateway for the frontend, handling requests for data and authentication.
*   **Ingestion Service:** A service responsible for receiving and queuing raw data from various collectors.
*   **Processing Service:** A worker that consumes data from the queue, processes it, generates embeddings, and stores the results in the database.
*   **Postgres Database:** A PostgreSQL database with the pgvector extension for storing all project data, including embeddings for similarity search.
*   **RabbitMQ:** A message broker used for asynchronous communication between the ingestion and processing services.
*   **Scheduler:** A service that triggers daily batch processing jobs.

## Installation

### Prerequisites

*   Docker and Docker Compose
*   Python 3.10+ and Pip
*   Node.js and npm

### Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/lifelog.git
    cd lifelog
    ```

2.  **Set up environment variables:**
    Copy the `.env.example` file to `.env` and fill in the required values, such as your `GEMINI_API_KEY`.
    ```bash
    cp .env.example .env
    ```

3.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install frontend dependencies:**
    ```bash
    cd frontend
    npm install
    cd ..
    ```

## Running the Application

The entire application stack can be run using Docker Compose:

```bash
docker-compose up --build
```

This will build the Docker images for each service and start the containers. The frontend will be accessible at `http://localhost:5173`.

## Development

For development, you can run the services individually.

*   **Backend Services:**
    Each service can be run from its respective directory. Ensure the database and RabbitMQ are running (e.g., via Docker Compose).

*   **Frontend:**
    ```bash
    cd frontend
    npm run dev
    ```
