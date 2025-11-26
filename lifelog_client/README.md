# LifeLog Client

The LifeLog Client runs on your machine to collect data and sync it with the LifeLog Server.

## Installation & Setup

1.  **Configure the Client**:
    Run the installation script to connect to your server and register the device.
    ```bash
    python3 install.py
    ```

2.  **Setup Auto-start (macOS)**:
    To make the client run automatically in the background and start on login:
    ```bash
    python3 setup_macos.py
    ```
    This script will:
    - Create a virtual environment and install dependencies if needed.
    - Create a Launch Agent plist file in `~/Library/LaunchAgents/`.
    - Load the job to start the client immediately.

## Management

-   **Check Status**:
    The client runs in the background. You can check if it's running via Activity Monitor or terminal:
    ```bash
    ps aux | grep lifelog_client
    ```

-   **Logs**:
    Logs are stored in `~/.lifelog/`:
    -   `~/.lifelog/client.log`: Standard output
    -   `~/.lifelog/client.err`: Error logs

-   **Stop the Service**:
    ```bash
    launchctl unload ~/Library/LaunchAgents/com.lifelog.client.plist
    ```

-   **Restart the Service**:
    ```bash
    launchctl unload ~/Library/LaunchAgents/com.lifelog.client.plist
    launchctl load ~/Library/LaunchAgents/com.lifelog.client.plist
    ```

## Development

The client uses a virtual environment for dependencies.
To activate it:
```bash
source .venv/bin/activate
```
