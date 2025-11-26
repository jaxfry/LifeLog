import pytest
from httpx import AsyncClient
from app.core.scheduler import start_scheduler, stop_scheduler

@pytest.mark.asyncio
async def test_get_scheduler_jobs(mock_superuser, async_client: AsyncClient):
    start_scheduler()
    try:
        response = await async_client.get("/api/v1/scheduler/jobs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # We expect at least the 3 default jobs
        assert len(data) >= 3
        
        job_names = [job["name"] for job in data]
        assert "run_processing_job" in job_names
        assert "run_daily_summary_job" in job_names
        assert "run_chapter_summary_job" in job_names
    finally:
        stop_scheduler()
