import json
import os
import subprocess
import sys
import resource
import shlex
from pathlib import Path
from typing import Any, Optional

from .config import settings

class IsolationError(Exception):
    pass


def _limit_resources():
    # Note: RLIMIT_AS may not be enforced identically across OSes; works in Docker Linux.
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (settings.EXT_ACTOR_MAX_CPU_SECONDS, settings.EXT_ACTOR_MAX_CPU_SECONDS))
    except Exception:
        pass
    try:
        mem_bytes = settings.EXT_ACTOR_MAX_MEMORY_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except Exception:
        pass


def _build_env(allow_network: bool) -> dict[str, str]:
    env = os.environ.copy()
    env['LIFELOG_NO_NETWORK'] = '1' if not allow_network else '0'
    # Set a path to sitecustomize that disables network if requested
    site_dir = str(Path(__file__).parent)
    pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = site_dir + (os.pathsep + pythonpath if pythonpath else '')
    return env


def run_external_actor(ext_dir: Path, actor_slug: str, payload: dict, *, allow_network: bool = False) -> dict:
    """
    Launch a sandboxed subprocess that imports the extension code and runs the actor
    via the standard worker entrypoint. Communication is JSON over stdin/stdout.
    """
    worker = Path(__file__).parent / 'isolated_worker.py'
    if not worker.exists():
        raise IsolationError("isolated_worker.py not found")

    cmd = [sys.executable, str(worker), '--ext-dir', str(ext_dir), '--actor', actor_slug]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_build_env(allow_network=allow_network),
        preexec_fn=_limit_resources if hasattr(resource, 'setrlimit') else None,
    )

    try:
        inn = json.dumps(payload) + "\n"
        out, err = proc.communicate(input=inn, timeout=settings.EXT_ACTOR_MAX_CPU_SECONDS + 5)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise IsolationError("Actor process timed out")

    if proc.returncode != 0:
        detail = err.strip()
        if (out or '').strip():
            try:
                j = json.loads(out)
                if isinstance(j, dict) and 'error' in j:
                    detail = f"{detail} {j['error']}".strip()
            except Exception:
                # include raw stdout if not JSON
                detail = f"{detail} {out.strip()}".strip()
        raise IsolationError(f"Actor process exited with code {proc.returncode}: {detail}")

    try:
        return json.loads(out or '{}')
    except json.JSONDecodeError as e:
        raise IsolationError(f"Invalid JSON from actor: {e}")
