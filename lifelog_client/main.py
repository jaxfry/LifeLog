import sys
import threading
import time
import logging
from pathlib import Path
from PIL import Image, ImageDraw
import pystray
from core.config import config_manager
from core.sync_engine import sync_engine
from core.extension_manager import extension_manager
import schedule

LOG_DIR = Path.home() / ".lifelog"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "client.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def create_icon():
    # Create a simple icon
    width = 64
    height = 64
    color1 = "black"
    color2 = "white"
    
    image = Image.new('RGB', (width, height), color1)
    dc = ImageDraw.Draw(image)
    dc.rectangle(
        (width // 2, 0, width, height // 2),
        fill=color2)
    dc.rectangle(
        (0, height // 2, width // 2, height),
        fill=color2)
    
    return image

def on_quit(icon, item):
    icon.stop()
    sync_engine.stop()
    sys.exit(0)

def on_sync(icon, item):
    logger.info("Manual sync triggered")
    # Run sync in a separate thread to not block the UI
    threading.Thread(target=sync_engine._sync_batch).start()

def on_config(icon, item):
    # In a real app, this might open a GUI window or the config file
    logger.info(f"Config file is at: {config_manager.config_file}")

def background_loop():
    """
    Main background loop for scheduling tasks
    """
    # Initial check for updates (Download extensions on startup)
    logger.info("Performing initial extension sync...")
    extension_manager.check_for_updates()

    # Schedule extension updates
    schedule.every(6).hours.do(extension_manager.check_for_updates)
    
    # Start collectors (Ensure they are running even if no updates were found)
    # Note: If updates were found, they might have been started by check_for_updates.
    # We check if they are already running to avoid double-restart.
    if not extension_manager.processes:
        extension_manager.start_collectors()
    
    # Start sync engine
    sync_engine.start()
    
    while True:
        schedule.run_pending()
        time.sleep(1)

def main():
    if not config_manager.is_configured:
        print("LifeLog Client is not configured. Please run 'python install.py' first.")
        return

    # Start background thread
    bg_thread = threading.Thread(target=background_loop, daemon=True)
    bg_thread.start()

    # Setup System Tray
    icon = pystray.Icon(
        "LifeLog",
        create_icon(),
        "LifeLog Client",
        menu=pystray.Menu(
            pystray.MenuItem("Sync Now", on_sync),
            pystray.MenuItem("Open Config", on_config),
            pystray.MenuItem("Quit", on_quit)
        )
    )
    
    logger.info("LifeLog Client started.")
    icon.run()

if __name__ == "__main__":
    main()