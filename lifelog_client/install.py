import sys
import requests
import click
from core.config import config_manager

@click.command()
def install():
    click.echo("Welcome to LifeLog Client Setup")
    
    if config_manager.is_configured:
        if not click.confirm("Client is already configured. Do you want to reconfigure?"):
            return

    server_url = click.prompt("Server URL", default="http://localhost:8000")
    # Validate connection
    try:
        # Just checking if server is reachable. 
        # Ideally check a health endpoint, but root or docs might work.
        requests.get(f"{server_url}/docs", timeout=5)
        click.echo("Successfully connected to server.")
    except requests.RequestException:
        click.echo("Could not connect to server. Please check the URL.")
        if not click.confirm("Continue anyway?"):
            return

    device_name = click.prompt("Device Name", default="My Desktop")
    device_type = click.prompt("Device Type", default="desktop")

    # Authenticate as Admin to register device
    click.echo("\nAuthentication Required (Admin Credentials)")
    username = click.prompt("Username")
    password = click.prompt("Password", hide_input=True)

    try:
        # 1. Get Token
        auth_response = requests.post(
            f"{server_url}/api/v1/token",
            data={"username": username, "password": password},
            timeout=10
        )
        auth_response.raise_for_status()
        token = auth_response.json()["access_token"]
        
        # 2. Register Device
        payload = {
            "name": device_name,
            "type": device_type
        }
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.post(
            f"{server_url}/api/v1/devices", 
            json=payload, 
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        device_id = data["device_id"]
        api_key = data["api_key"]
        
        config_manager.save_config(
            server_url=server_url,
            device_id=device_id,
            api_key=api_key,
            device_name=device_name,
            device_type=device_type
        )
        
        click.echo(f"Device registered successfully! ID: {device_id}")
        click.echo("Configuration saved to ~/.lifelog/config.json")
        
    except requests.RequestException as e:
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code == 401:
                click.echo("Authentication failed: Invalid username or password.")
            elif e.response.status_code == 403:
                click.echo("Permission denied: Only admins can register devices.")
            else:
                click.echo(f"Registration failed: {e.response.status_code} - {e.response.text}")
        else:
            click.echo(f"Connection error: {e}")
        return

if __name__ == "__main__":
    install()