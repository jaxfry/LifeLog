from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

CONFIG_DIR = Path.home() / ".lifelog" / "agent"
CONFIG_PATH = CONFIG_DIR / "config.json"


class AgentConfig(BaseModel):
    server_url: str
    device_key: str
    platform: str = "macos"
    poll_interval_sec: int = 300
    max_queue_mb: int = 50
    # Arbitrary nested collector config mirrored from server
    collectors: Dict[str, Dict[str, Dict[str, Any]]] = Field(default_factory=dict)

    @staticmethod
    def load() -> "AgentConfig":
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text())
            return AgentConfig.model_validate(data)
        raise FileNotFoundError(f"Config not found at {CONFIG_PATH}")

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(self.model_dump_json(indent=2))

    def merge_server_config(self, server_cfg: Dict[str, Any]) -> None:
        # Shallow merge top-level agent settings and collectors block
        agent = server_cfg.get("agent") or {}
        if isinstance(agent, dict):
            if "poll_interval_sec" in agent:
                self.poll_interval_sec = int(agent["poll_interval_sec"])  
        collectors = server_cfg.get("collectors") or {}
        if isinstance(collectors, dict):
            # deep-ish merge ext/collector maps
            for ext_slug, col_map in collectors.items():
                if not isinstance(col_map, dict):
                    continue
                cur = self.collectors.get(ext_slug, {})
                for col_slug, cfg in col_map.items():
                    if isinstance(cfg, dict):
                        cur[col_slug] = {**cur.get(col_slug, {}), **cfg}
                self.collectors[ext_slug] = cur
