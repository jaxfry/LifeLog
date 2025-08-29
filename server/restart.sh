docker-compose down -v
docker-compose up -d --build
pnpm --filter @lifelog/server db:upgrade 
curl -X POST "http://127.0.0.1:8000/extensions/" \
-H "Content-Type: application/json" \
-d '{
      "slug": "test-extension",
      "name": "Test Extension",
      "version": "1.0.0",
      "actors": [
        {
          "slug": "test-source",
          "actor_type": "SOURCE",
          "version": "1.0.0"
        },
        {
          "slug": "test-processor",
          "actor_type": "PROCESSOR",
          "version": "1.0.0"
        }
      ]
    }'
curl -X POST "http://127.0.0.1:8000/ingest/" \
-H "Content-Type: application/json" \
-d '{
      "source_actor_slug": "test-source",
      "data": {
        "message": "Live test of the full data pipeline!",
        "value": 123
      }
    }'