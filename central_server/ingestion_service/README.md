# Data Ingestion Service

## Purpose

This service is a component of the LifeLog central server. Its primary responsibility is to:
1.  Receive raw data payloads from local daemons.
2.  Validate the data format and integrity using Pydantic models.
3.  Publish the validated data as a JSON message to a RabbitMQ queue (e.g., `lifelog_events_queue`) for asynchronous processing by other services.

## Prerequisites

*   Python 3.8+
*   RabbitMQ server running and accessible.
*   Docker (if running as part of Docker Compose setup).

## Running the Service

This service is designed to be run as part of the `docker-compose.yml` setup in the project root.

1.  **Using Docker Compose (Recommended):**
    *   Navigate to the project root directory.
    *   Ensure Docker and Docker Compose are installed.
    *   Run `docker-compose up --build`.
    *   The service will be built from its Dockerfile and started by Docker Compose.
    *   Environment variables like `RABBITMQ_HOST` will be automatically configured by Docker Compose to point to the `rabbitmq` service.
    *   The service will typically be accessible on a mapped port (e.g., `http://localhost:8001` if mapped from container port 8000). Check the root `docker-compose.yml` for specific port mappings.

2.  **Running Standalone (for development/testing outside Docker Compose):**
    *   **Navigate to the service directory:**
        ```bash
        cd central_server/ingestion_service
        ```
    *   **Set up RabbitMQ (if not already running):**
        A simple way to run RabbitMQ for development is using Docker:
        ```bash
        docker run -d --hostname my-rabbit --name some-rabbit -p 5672:5672 -p 15672:15672 rabbitmq:3-management
        ```
        This will start a RabbitMQ instance with the management plugin enabled on port 15672 (guest/guest for credentials). The service will connect to RabbitMQ on port 5672.
    *   **Install dependencies:**
        It's recommended to use a virtual environment.
        ```bash
        python -m venv venv
        source venv/bin/activate  # On Windows use `venv\Scripts\activate`
        pip install -r requirements.txt
        ```
    *   **Configure Environment Variables:**
        The service can be configured using the following environment variables if running standalone. When run with Docker Compose, these are typically set in the `docker-compose.yml` file.
        *   `RABBITMQ_HOST`: Hostname of the RabbitMQ server (default: `localhost`).
        *   `RABBITMQ_PORT`: Port of the RabbitMQ server (default: `5672`).
        *   `RABBITMQ_QUEUE`: Name of the RabbitMQ queue to publish to (default: `lifelog_events_queue`).
        Example:
        ```bash
        export RABBITMQ_HOST=localhost # or your RabbitMQ server address
        export RABBITMQ_PORT=5672
        ```
    *   **Run the FastAPI application using Uvicorn:**
        ```bash
        uvicorn main:app --reload --port 8000 # Or another port like 8001 if 8000 is in use
        ```
        The service will be available at `http://localhost:8000` (or the port you chose).

## API Endpoint

### `/api/v1/ingest`

*   **Method:** `POST`
*   **Description:** Accepts JSON payloads containing log events from local daemons.
*   **Request Body (JSON):**

    The expected payload should conform to the following structure:

    ```json
    {
      "events": [
        {
          "timestamp": "2023-10-27T10:30:00Z",
          "type": "application_focus",
          "data": {
            "application_name": "VS Code",
            "window_title": "main.py - MyProject"
          }
        },
        {
          "timestamp": "2023-10-27T10:30:05Z",
          "type": "keyboard_activity",
          "data": {
            "keys_pressed": 15
          }
        }
      ],
      "source_id": "daemon-instance-12345"
    }
    ```

    *   `events`: A list of event objects.
        *   `timestamp`: An ISO 8601 formatted datetime string (UTC).
        *   `type`: A string indicating the type of event (e.g., "application_focus", "mouse_activity").
        *   `data`: A dictionary containing event-specific data.
    *   `source_id`: A string identifying the local daemon instance that sent the data.

*   **Success Response (200 OK):**

    ```json
    {
        "status": "success",
        "message": "Data received and published to RabbitMQ.",
        "source_id": "daemon-instance-12345",
        "received_events": 2,
        "ingestion_timestamp": "2023-10-27T10:35:00.123456+00:00"
    }
    ```

*   **Error Response (503 Service Unavailable):**
    If the service fails to publish the data to RabbitMQ.
    ```json
    {
        "detail": "Failed to publish data to message queue. Please try again later."
    }
    ```

*   **Error Response (422 Unprocessable Entity):**
    If the payload validation fails (e.g., missing fields, incorrect data types). The response body will contain details about the validation errors.

    ```json
    {
        "detail": [
            {
                "loc": [
                    "body",
                    "events",
                    0,
                    "timestamp"
                ],
                "msg": "invalid datetime format",
                "type": "value_error.datetime"
            }
        ]
    }
    ```
*   **Error Response (500 Internal Server Error):**
    For unexpected server-side errors.