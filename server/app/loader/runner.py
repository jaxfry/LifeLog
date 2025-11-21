import importlib.util
import sys
import os
from typing import Dict, Any, List

# Define extensions directory relative to this file
# server/app/loader/runner.py -> server/extensions
EXTENSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../extensions"))

def run_normalization(extension_id: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Runs the normalize function of an extension.
    Dynamically loads the module from the extensions directory.
    """
    # Construct path to processor.py
    extension_path = os.path.join(EXTENSIONS_DIR, extension_id, "processor.py")
    
    if not os.path.exists(extension_path):
        # Fallback for development/testing if running from different CWD
        # Try looking in current directory/extensions
        alt_path = os.path.join(os.getcwd(), "extensions", extension_id, "processor.py")
        if os.path.exists(alt_path):
            extension_path = alt_path
        else:
            raise FileNotFoundError(f"Extension processor not found at {extension_path}")

    # Load module from file path
    spec = importlib.util.spec_from_file_location(f"extensions.{extension_id}.processor", extension_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"extensions.{extension_id}.processor"] = module
        spec.loader.exec_module(module)
        
        if hasattr(module, "normalize"):
            return module.normalize(payload)
        else:
            raise AttributeError(f"Extension {extension_id} has no 'normalize' function")
            
    return []
