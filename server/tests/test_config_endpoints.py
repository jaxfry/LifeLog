import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import engine

@pytest.mark.asyncio
async def test_config_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. List Config (Should contain GEMINI_API_KEY from seeding)
        response = await ac.get("/api/v1/config")
        assert response.status_code == 200
        configs = response.json()
        assert isinstance(configs, list)
        
        # Check if GEMINI_API_KEY is present (it was seeded)
        gemini_config = next((c for c in configs if c["key"] == "GEMINI_API_KEY"), None)
        assert gemini_config is not None
        assert gemini_config["value"] == "AIzaSyCxz6dnFwpEGyGgpXqU3x7TFQSq7casaT0"

        # 2. Update Config
        new_desc = "Updated Description"
        response = await ac.put(
            "/api/v1/config/GEMINI_API_KEY", 
            json={"value": "AIzaSyCxz6dnFwpEGyGgpXqU3x7TFQSq7casaT0", "description": new_desc}
        )
        assert response.status_code == 200
        updated_config = response.json()
        assert updated_config["description"] == new_desc
        
        # 3. Create New Config
        new_key = "TEST_SETTING"
        new_val = "test_value"
        response = await ac.put(
            f"/api/v1/config/{new_key}",
            json={"value": new_val, "description": "A test setting"}
        )
        assert response.status_code == 200
        created_config = response.json()
        assert created_config["key"] == new_key
        assert created_config["value"] == new_val
        
        # 4. Verify Persistence
        response = await ac.get("/api/v1/config")
        configs = response.json()
        test_config = next((c for c in configs if c["key"] == new_key), None)
        assert test_config is not None
        assert test_config["value"] == new_val
