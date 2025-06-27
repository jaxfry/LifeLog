# LifeLog API Service

A unified FastAPI service that provides authentication, data management, and analytics for the LifeLog application.

## Features

- **Authentication**: JWT-based authentication with user registration and login
- **Projects Management**: CRUD operations for projects with smart categorization
- **Timeline Management**: View and manage timeline entries with daily summaries
- **Events Management**: Handle raw events from various data sources
- **Daily Analytics**: Get comprehensive daily statistics and insights
- **System Management**: Background processing and system status monitoring

## Architecture

The API service uses:
- **FastAPI** for the web framework
- **PostgreSQL** with **pgvector** for data storage and embeddings
- **SQLAlchemy** with async support for database operations
- **JWT tokens** for authentication
- **RabbitMQ** for message queuing (integration with processing service)
- **Pydantic** for data validation and serialization

## API Endpoints

### Authentication (`/api/v1/auth`)
- `POST /token` - Login and receive JWT token
- `POST /register` - Register new user
- `GET /me` - Get current user information

### Projects (`/api/v1/projects`)
- `GET /` - List all projects (with pagination)
- `POST /` - Create new project
- `GET /{project_id}` - Get specific project
- `PUT /{project_id}` - Update project
- `DELETE /{project_id}` - Delete project

### Timeline (`/api/v1/timeline`)
- `GET /` - Get timeline entries (with filtering)
- `GET /{entry_id}` - Get specific timeline entry

### Events (`/api/v1/events`)
- `GET /` - Get events (with filtering by time, source, type)
- `GET /{event_id}` - Get specific event

### Daily Data (`/api/v1/day`)
- `GET /{date}` - Get comprehensive day data (timeline + stats)

### System (`/api/v1/system`)
- `GET /status` - Get system status
- `POST /process-now` - Trigger immediate processing

## Running the Service

### With Docker Compose (Recommended)

The API service is included in the main docker-compose.yml:

```bash
# From the project root
docker-compose up --build
```

The API will be available at `http://localhost:8000`

### Development Mode

1. Install dependencies:
```bash
cd central_server/api_service
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export POSTGRES_HOST=localhost
export POSTGRES_USER=lifelog
export POSTGRES_PASSWORD=lifelogpassword
export POSTGRES_DB=lifelog
export SECRET_KEY=your-secret-key-here
```

3. Run the service:
```bash
uvicorn main:app --reload --port 8000
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_HOST` | PostgreSQL host | `localhost` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `POSTGRES_USER` | PostgreSQL username | `lifelog` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `lifelogpassword` |
| `POSTGRES_DB` | PostgreSQL database name | `lifelog` |
| `SECRET_KEY` | JWT secret key | `your-secret-key-change-in-production` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token expiration | `30` |
| `RABBITMQ_HOST` | RabbitMQ host | `localhost` |
| `RABBITMQ_PORT` | RabbitMQ port | `5672` |
| `RABBITMQ_USER` | RabbitMQ username | `user` |
| `RABBITMQ_PASS` | RabbitMQ password | `password` |
| `DEBUG` | Enable debug mode | `false` |

## API Documentation

When running, visit:
- **Swagger UI**: `http://localhost:8000/api/v1/docs`
- **ReDoc**: `http://localhost:8000/api/v1/redoc`

## Authentication

The API uses JWT tokens for authentication. To access protected endpoints:

1. Register or login to get a token:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin&password=admin123"
```

2. Use the token in subsequent requests:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     "http://localhost:8000/api/v1/projects"
```

## Database Schema

The service uses the PostgreSQL schema defined in `postgres/init/02_schema.sql`, which includes:

- `users` - User accounts
- `projects` - Project categories
- `project_aliases` - Alternative names for projects
- `events` - Raw event data
- `timeline_entries` - Processed timeline entries
- `digital_activity_data` - Detailed digital activity information

## Integration

This API service integrates with:
- **Ingestion Service** - Receives processed data via database
- **Processing Service** - Shares database for processed results
- **Frontend** - Provides data for the React application
- **Local Daemons** - Indirectly via the ingestion service

## Health Monitoring

- Health check endpoint: `GET /health`
- System status endpoint: `GET /api/v1/system/status`

## Development

### Adding New Endpoints

1. Create endpoint file in `api_v1/endpoints/`
2. Add router to `main.py`
3. Update schemas in `schemas.py` if needed
4. Add database models in `core/models.py` if needed

### Testing

The service includes comprehensive error handling and input validation. Test endpoints using:
- The built-in Swagger UI at `/api/v1/docs`
- Tools like curl, Postman, or httpie
- The frontend application

## Security

- Passwords are hashed using bcrypt
- JWT tokens are used for stateless authentication
- SQL injection protection via SQLAlchemy
- Input validation via Pydantic
- CORS configuration for frontend integration
