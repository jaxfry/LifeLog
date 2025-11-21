import time
import requests
import logging
import os
import json
import subprocess
import zipfile
import io
import sys
import shutil
import threading
from pathlib import Path
from typing import Optional, Dict, List
from .config import config_manager
from .database import db_manager

logger = logging.getLogger(__name__)

EXTENSIONS_DIR = Path(__file__).parent.parent / "extensions"

class ExtensionManager:
    def __init__(self):
        self.manifest_hash: Optional[str] = None
        self.processes: Dict[str, subprocess.Popen] = {}
        self._ensure_extensions_dir()

    def _ensure_extensions_dir(self):
        if not EXTENSIONS_DIR.exists():
            EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)

    def _monitor_process(self, ext_id: str, process: subprocess.Popen):
        """
        Reads stdout from the collector process and pushes to DB.
        """
        logger.info(f"Started monitoring thread for {ext_id}")
        
        if process.stdout is None:
            logger.error(f"[{ext_id}] Process stdout is None, cannot monitor.")
            return

        try:
            # Read line by line
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue

                try:
                    # Parse JSON
                    payload = json.loads(line)
                    
                    # Push to Local Buffer
                    db_manager.push(extension_id=ext_id, payload=payload)
                    logger.debug(f"Captured event from {ext_id}")
                    
                except json.JSONDecodeError:
                    logger.warning(f"[{ext_id}] Invalid JSON output: {line}")
                except Exception as e:
                    logger.error(f"[{ext_id}] Error processing output: {e}")
                    
        except Exception as e:
            logger.error(f"Error monitoring {ext_id}: {e}")
        finally:
            logger.info(f"Monitoring thread for {ext_id} stopped")
            if process.poll() is not None:
                logger.error(f"[{ext_id}] Process exited with code {process.returncode}")
                if process.stderr:
                    stderr_output = process.stderr.read()
                    if stderr_output:
                        logger.error(f"[{ext_id}] Stderr: {stderr_output}")

    def start_collectors(self):
        """
        Loop through extensions/ and run them.
        """
        logger.info("Starting collectors...")
        self._ensure_extensions_dir()
        
        # Stop existing processes first (simple reload strategy)
        self.stop_collectors()

        if not any(os.scandir(EXTENSIONS_DIR)):
            logger.info("No extensions installed. Waiting for sync...")
            return

        for ext_id in os.listdir(EXTENSIONS_DIR):
            ext_path = EXTENSIONS_DIR / ext_id
            if not ext_path.is_dir():
                continue
            
            manifest_path = ext_path / "manifest.json"
            if not manifest_path.exists():
                logger.warning(f"No manifest found for {ext_id}, skipping.")
                continue
                
            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
                
                client_config = manifest.get("client", {})
                if client_config.get("type") != "python":
                    logger.info(f"Skipping non-python extension {ext_id}")
                    continue
                
                script_file = client_config.get("file")
                if not script_file:
                    logger.warning(f"No script file defined for {ext_id}")
                    continue
                
                script_path = ext_path / script_file
                if not script_path.exists():
                    logger.warning(f"Script {script_file} not found for {ext_id}")
                    continue
                
                # Prepare Environment Variables
                env = os.environ.copy()
                env["LIFELOG_API_KEY"] = config_manager.get("api_key", "")
                env["LIFELOG_SERVER_URL"] = config_manager.get("server_url", "")
                env["LIFELOG_DEVICE_ID"] = config_manager.get("device_id", "")
                # Add extension directory to PYTHONPATH so it can import local modules if needed
                env["PYTHONPATH"] = str(ext_path) + os.pathsep + env.get("PYTHONPATH", "")

                # Spawn Process
                logger.info(f"Spawning collector for {ext_id}: {script_file}")
                proc = subprocess.Popen(
                    [sys.executable, str(script_path)],
                    cwd=str(ext_path),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, # We could also monitor stderr in a separate thread
                    text=True,
                    bufsize=1 # Line buffered
                )
                self.processes[ext_id] = proc
                
                # Start Monitoring Thread
                monitor_thread = threading.Thread(
                    target=self._monitor_process,
                    args=(ext_id, proc),
                    daemon=True
                )
                monitor_thread.start()
                
            except Exception as e:
                logger.error(f"Failed to start collector for {ext_id}: {e}")

    def stop_collectors(self):
        for ext_id, proc in self.processes.items():
            logger.info(f"Stopping collector {ext_id}...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.processes.clear()

    def check_for_updates(self):
        """
        Poll GET /api/v1/client/extensions every 6 hours (or as scheduled).
        """
        if not config_manager.is_configured:
            return

        logger.info("Checking for extension updates...")
        try:
            self.sync_extensions()
        except Exception as e:
            logger.error(f"Failed to check for updates: {e}")

    def sync_extensions(self):
        """
        Download new files and restart collectors.
        """
        server_url = config_manager.get("server_url")
        try:
            response = requests.get(f"{server_url}/api/v1/client/extensions", timeout=10)
            if response.status_code != 200:
                logger.error(f"Failed to list extensions: {response.status_code}")
                return
            
            extensions = response.json()
            changes_made = False
            
            for ext in extensions:
                ext_id = ext["id"]
                # Check if we need to download
                # For simplicity, we always download if it's not there, 
                # or if we want to force update. 
                # Ideally we check version.
                
                ext_dir = EXTENSIONS_DIR / ext_id
                manifest_path = ext_dir / "manifest.json"
                
                needs_download = True
                if ext_dir.exists() and manifest_path.exists():
                    try:
                        with open(manifest_path, "r") as f:
                            local_manifest = json.load(f)
                        if local_manifest.get("version") == ext.get("version"):
                            needs_download = False
                    except:
                        pass
                
                if needs_download:
                    logger.info(f"Downloading extension {ext_id}...")
                    self._download_extension(server_url, ext_id)
                    changes_made = True
            
            if changes_made:
                logger.info("Extensions updated. Restarting collectors...")
                self.start_collectors()
                
        except requests.RequestException as e:
            logger.error(f"Network error during sync: {e}")

    def _download_extension(self, server_url: str, ext_id: str):
        try:
            resp = requests.get(f"{server_url}/api/v1/client/download/{ext_id}", stream=True, timeout=30)
            if resp.status_code == 200:
                z = zipfile.ZipFile(io.BytesIO(resp.content))
                target_dir = EXTENSIONS_DIR / ext_id
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                target_dir.mkdir(parents=True, exist_ok=True)
                z.extractall(target_dir)
                logger.info(f"Installed {ext_id}")
            else:
                logger.error(f"Failed to download {ext_id}: {resp.status_code}")
        except Exception as e:
            logger.error(f"Error downloading {ext_id}: {e}")

extension_manager = ExtensionManager()