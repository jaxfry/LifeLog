import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

CONFIG_DIR = Path.home() / ".lifelog"
CONFIG_FILE = CONFIG_DIR / "config.json"

class ConfigManager:
    def __init__(self):
        self.config_dir = CONFIG_DIR
        self.config_file = CONFIG_FILE
        self._ensure_config_dir()
        self.config = self._load_config()

    def _ensure_config_dir(self):
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def save_config(self, server_url: str, device_id: str, api_key: str, device_name: str, device_type: str):
        self.config = {
            "server_url": server_url.rstrip("/"),
            "device_id": device_id,
            "api_key": api_key,
            "device_name": device_name,
            "device_type": device_type
        }
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=4)

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    @property
    def is_configured(self) -> bool:
        return all(k in self.config for k in ["server_url", "device_id", "api_key"])

config_manager = ConfigManager()