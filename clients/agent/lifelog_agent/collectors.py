from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .config import AgentConfig, CONFIG_DIR
from .queue import OfflineQueue
from .http import DeviceClient

class CollectorProcess:
    def __init__(self, *, slug: str, ext_slug: str, entrypoint: Path, env: Dict[str, str]):
        self.slug = slug
        self.ext_slug = ext_slug
        self.entrypoint = entrypoint
        self.env = env
        self.proc: Optional[asyncio.subprocess.Process] = None

    async def start(self):
        python = sys.executable
        self.proc = await asyncio.create_subprocess_exec(
            python, str(self.entrypoint),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **self.env},
            cwd=str(self.entrypoint.parent),
        )

    async def stop(self):
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.proc.kill()

    async def read_stdout(self):
        if not self.proc or not self.proc.stdout:
            return None
        line = await self.proc.stdout.readline()
        if not line:
            return None
        try:
            return json.loads(line.decode().strip())
        except Exception:
            return {"type": "status", "level": "warn", "message": f"invalid_json: {line!r}"}


class CollectorSupervisor:
    def __init__(self, cfg: AgentConfig, client: DeviceClient, queue: OfflineQueue):
        self.cfg = cfg
        self.client = client
        self.queue = queue
        self.tasks: dict[str, asyncio.Task] = {}

    async def _run_collector(self, ext_slug: str, collector_slug: str, entrypoint: Path):
        # Use collector slug as source actor slug per MVP assumption
        source_actor_slug = collector_slug
        col_cfg = self.cfg.collectors.get(ext_slug, {}).get(collector_slug, {})
        env = {
            "LIFELOG_SERVER_URL": self.cfg.server_url,
            "LIFELOG_SOURCE_ACTOR_SLUG": source_actor_slug,
            "LIFELOG_COLLECTOR_CONFIG_JSON": json.dumps(col_cfg),
        }
        proc = CollectorProcess(slug=collector_slug, ext_slug=ext_slug, entrypoint=entrypoint, env=env)
        await proc.start()

        backoff = 1
        while True:
            msg = await proc.read_stdout()
            if msg is None:
                # process likely exited
                code = proc.proc.returncode if proc.proc else -1
                if code is None:
                    await asyncio.sleep(0.5)
                    continue
                # restart with backoff
                await proc.stop()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                await proc.start()
                continue
            kind = msg.get("type")
            if kind == "raw_log":
                data = msg.get("data") or {}
                self.queue.enqueue("ingest", {"source_actor_slug": source_actor_slug, "data": data})
            else:
                # status or unknown
                # could log to a file later
                pass

    def ensure_running(self, ext_slug: str, collector_slug: str, entrypoint: Path):
        key = f"{ext_slug}:{collector_slug}"
        if key in self.tasks and not self.tasks[key].done():
            return
        self.tasks[key] = asyncio.create_task(self._run_collector(ext_slug, collector_slug, entrypoint))
