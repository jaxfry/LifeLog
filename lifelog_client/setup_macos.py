import os
import sys
import plistlib
import subprocess
from pathlib import Path

def setup_macos_autostart():
    if sys.platform != 'darwin':
        print("This script is intended for macOS only.")
        return

    # Define paths
    current_dir = Path(__file__).parent.absolute()
    main_script = current_dir / "main.py"
    venv_dir = current_dir / ".venv"
    venv_python = venv_dir / "bin" / "python"
    requirements_file = current_dir / "requirements.txt"

    # Create virtual environment if it doesn't exist
    if not venv_python.exists():
        print("Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        
        # Install requirements
        if requirements_file.exists():
            print("Installing dependencies...")
            subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(requirements_file)], check=True)
    
    python_executable = str(venv_python)
    print(f"Using python: {python_executable}")
    
    label = "com.lifelog.client"
    plist_name = f"{label}.plist"
    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    plist_path = launch_agents_dir / plist_name
    
    # Ensure LaunchAgents directory exists
    launch_agents_dir.mkdir(parents=True, exist_ok=True)
    
    # Create plist content
    plist_content = {
        "Label": label,
        "ProgramArguments": [
            python_executable,
            str(main_script)
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(current_dir),
        "StandardOutPath": str(Path.home() / ".lifelog" / "client.log"),
        "StandardErrorPath": str(Path.home() / ".lifelog" / "client.err"),
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
        }
    }
    
    # Ensure log directory exists
    log_dir = Path.home() / ".lifelog"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Write plist file
    print(f"Creating plist file at {plist_path}...")
    with open(plist_path, 'wb') as f:
        plistlib.dump(plist_content, f)
        
    # Unload existing job if it exists (ignore errors)
    try:
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False, capture_output=True)
    except Exception:
        pass

    # Load the new job
    print("Loading launchd job...")
    try:
        subprocess.run(["launchctl", "load", str(plist_path)], check=True)
        print("Successfully set up auto-start for LifeLog Client!")
        print(f"Logs will be available at {log_dir}")
    except subprocess.CalledProcessError as e:
        print(f"Error loading launchd job: {e}")

if __name__ == "__main__":
    setup_macos_autostart()
