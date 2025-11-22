import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import engine

@pytest.mark.asyncio
@pytest.mark.integration
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
        # assert gemini_config["value"] == "dummy_key_for_testing" # Value might be real in some envs

        # 2. Update Config
        # Use a test key to avoid messing with real config
        test_key = "TEST_CONFIG_KEY"
        
        # Create/Update a test config
        response = await ac.put(
            f"/api/v1/config/{test_key}", 
            json={"value": "initial_value", "description": "Initial Description"}
        )
        assert response.status_code == 200
        
        # Update it
        new_desc = "Updated Description"
        response = await ac.put(
            f"/api/v1/config/{test_key}", 
            json={"value": "initial_value", "description": new_desc}
        )
        assert response.status_code == 200
        updated_config = response.json()
        assert updated_config["description"] == new_desc
        
        # 3. Create New Config (Already covered above, but let's keep the flow)
        new_key = "TEST_SETTING_2"
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
