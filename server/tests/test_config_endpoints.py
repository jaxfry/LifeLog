import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import engine

@pytest.mark.asyncio
@pytest.mark.integration
async def test_config_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. List Config (Initially empty or with existing configs)
        response = await ac.get("/api/v1/config")
        assert response.status_code == 200
        configs = response.json()
        assert isinstance(configs, list)

        # 2. Create a test config key for testing
        # Use a dedicated test key instead of relying on seeded data
        test_key = "TEST_CONFIG_KEY"
        
        # Create a test config
        response = await ac.put(
            f"/api/v1/config/{test_key}", 
            json={"value": "initial_value", "description": "Initial Description"}
        )
        assert response.status_code == 200
        created = response.json()
        assert created["key"] == test_key
        assert created["value"] == "initial_value"
        
        # 3. Update Config
        new_desc = "Updated Description"
        response = await ac.put(
            f"/api/v1/config/{test_key}", 
            json={"value": "initial_value", "description": new_desc}
        )
        assert response.status_code == 200
        updated_config = response.json()
        assert updated_config["description"] == new_desc
        
        # 4. Create Another Config
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
        
        # 5. Verify Persistence - List all configs and verify both test keys exist
        response = await ac.get("/api/v1/config")
        configs = response.json()
        test_config = next((c for c in configs if c["key"] == test_key), None)
        assert test_config is not None
        assert test_config["description"] == new_desc
        
        test_config_2 = next((c for c in configs if c["key"] == new_key), None)
        assert test_config_2 is not None
        assert test_config_2["value"] == new_val
