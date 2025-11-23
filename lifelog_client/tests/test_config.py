import pytest
from unittest.mock import patch, mock_open
from lifelog_client.core.config import ConfigManager

@pytest.fixture
def mock_config_file(tmp_path):
    config_file = tmp_path / "config.json"
    with patch("lifelog_client.core.config.CONFIG_FILE", config_file):
        with patch("lifelog_client.core.config.CONFIG_DIR", tmp_path):
            yield config_file

def test_config_manager_init(mock_config_file):
    manager = ConfigManager()
    assert manager.config == {}
    assert not manager.is_configured

def test_save_and_load_config(mock_config_file):
    manager = ConfigManager()
    manager.save_config(
        server_url="http://test.com",
        device_id="dev1",
        api_key="key1",
        device_name="My Mac",
        device_type="laptop"
    )
    
    assert manager.get("server_url") == "http://test.com"
    assert manager.is_configured
    
    # Reload
    new_manager = ConfigManager()
    assert new_manager.get("device_id") == "dev1"

def test_is_configured_false(mock_config_file):
    manager = ConfigManager()
    manager.config = {"server_url": "http://test.com"} # Missing others
    assert not manager.is_configured
