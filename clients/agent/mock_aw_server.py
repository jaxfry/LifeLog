#!/usr/bin/env python3
"""
Mock ActivityWatch server for testing the LifeLog agent without running actual ActivityWatch.

This simple HTTP server mimics AW's API endpoints:
- GET /api/0/buckets - returns a list of window buckets
- GET /api/0/buckets/{bucket}/events - returns mock window events
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime, timezone, timedelta
import random

MOCK_BUCKETS = [
    {
        "id": "aw-watcher-window_testhost",
        "name": "aw-watcher-window_testhost",
        "type": "currentwindow",
        "client": "aw-watcher-window",
        "hostname": "testhost"
    }
]

MOCK_APPS = [
    {"app": "Code", "title": "LifeLog - Visual Studio Code"},
    {"app": "Chrome", "title": "GitHub - Google Chrome"},
    {"app": "Terminal", "title": "zsh"},
    {"app": "Slack", "title": "General - Slack"},
    {"app": "Spotify", "title": "Music Player"},
]


class MockAWHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/0/buckets":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(MOCK_BUCKETS).encode())
            return
        
        if self.path.startswith("/api/0/buckets/") and self.path.endswith("/events"):
            # Generate some mock events
            now = datetime.now(timezone.utc)
            events = []
            
            # Create 3-5 recent events
            for i in range(random.randint(3, 5)):
                event_time = now - timedelta(minutes=i * 5)
                app_data = random.choice(MOCK_APPS)
                events.append({
                    "timestamp": event_time.isoformat(),
                    "duration": random.randint(30, 300),  # 30s to 5min
                    "data": app_data
                })
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(events).encode())
            return
        
        self.send_response(404)
        self.end_headers()
    
    def log_message(self, format, *args):
        # Custom log format
        print(f"[MockAW] {format % args}")


if __name__ == "__main__":
    port = 5600
    server = HTTPServer(("127.0.0.1", port), MockAWHandler)
    print(f"🎭 Mock ActivityWatch server running on http://127.0.0.1:{port}")
    print("   This simulates ActivityWatch for testing the LifeLog agent")
    print("   Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down mock server")
        server.shutdown()
