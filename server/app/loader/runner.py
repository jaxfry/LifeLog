import importlib.util
import inspect
import os
import sys
from typing import Any

# Define extensions directory relative to this file
# server/app/loader/runner.py -> server/extensions
EXTENSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../extensions"))


def _load_extension_module(extension_id: str, filename: str):
    extension_path = os.path.join(EXTENSIONS_DIR, extension_id, filename)
    if not os.path.exists(extension_path):
        extension_path = os.path.join(os.getcwd(), "extensions", extension_id, filename)
    if not os.path.exists(extension_path):
        raise FileNotFoundError(f"Extension module not found at {extension_path}")
    module_name = f"extensions.{extension_id}.{filename.removesuffix('.py')}"
    spec = importlib.util.spec_from_file_location(module_name, extension_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {extension_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

def run_normalization(extension_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Runs the normalize function of an extension.
    Dynamically loads the module from the extensions directory.
    """
    module = _load_extension_module(extension_id, "processor.py")
    if not hasattr(module, "normalize"):
        raise AttributeError(f"Extension {extension_id} has no 'normalize' function")
    return module.normalize(payload)


async def run_poller(extension_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Run a trusted extension acquisition adapter; base owns persistence afterward."""
    module = _load_extension_module(extension_id, "poller.py")
    if not hasattr(module, "poll"):
        raise AttributeError(f"Extension {extension_id} has no 'poll' function")
    result = module.poll(config)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
        raise TypeError("poll() must return list[dict]")
    return result
