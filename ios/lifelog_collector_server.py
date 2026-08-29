#!/usr/bin/env python3
"""Collect-only inspection server for the LifeLog iOS app.

Accepts the endpoints the app calls and stores everything under ./collected/
for manual inspection. Serves a human-readable /inspect page.

Run:  uv run python3 lifelog_collector_server.py [port]
Prompt the app's Settings with:
  Server URL:     http://<this machine's LAN IP>:8000
  Device API key: any non-empty string
"""

import json
import re
import socket
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE = Path(__file__).parent / "collected"
BASE.mkdir(exist_ok=True)
(UPLOADS := BASE / "uploads").mkdir(exist_ok=True)

INGEST_FILE = BASE / "ingest.jsonl"
DRAFTS_FILE = BASE / "drafts.jsonl"
CHAT_FILE = BASE / "chat.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _html_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Handler(BaseHTTPRequestHandler):
    server_version = "LifeLogCollectOnly/0.1"

    def log_message(self, fmt, *args):  # quieter logs
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload) -> None:
        self._send(code, json.dumps(payload).encode())

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_GET(self):
        UPLOADS.mkdir(parents=True, exist_ok=True)
        path = urlparse(self.path).path
        if path in ("/", "/inspect"):
            self._page()
        elif path == "/health":
            self._json(200, {"ok": True})
        else:
            match = re.fullmatch(r"/api/v1/captures/([0-9A-Fa-f-]+)/uploads/([0-9A-Fa-f-]+)", path)
            if match:
                upload_id = match.group(2)
                received = (UPLOADS / upload_id).stat().st_size if (UPLOADS / upload_id).exists() else 0
                self._json(200, {"id": upload_id, "receivedBytes": received})
            else:
                self._json(404, {"detail": "not found"})

    def do_POST(self):
        UPLOADS.mkdir(parents=True, exist_ok=True)
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/api/v1/ingest":
            record = self._decode(body)
            record["received_at"] = _now()
            record["api_key"] = self.headers.get("X-API-Key", "")
            _append_jsonl(INGEST_FILE, record)
            print(f"+ ingest {record.get('client_timestamp', '?')} "
                  f"type={record.get('payload', {}).get('type')} id={record.get('payload', {}).get('id')}")
            self._json(200, {"ok": True})

        elif path == "/api/v1/captures/drafts":
            draft = self._decode(body)
            draft["received_at"] = _now()
            draft["capture_id"] = str(uuid.uuid4())
            _append_jsonl(DRAFTS_FILE, draft)
            print(f"+ draft {draft['capture_id']} kind={draft.get('kind')}")
            self._json(201, {"capture": {"id": draft["capture_id"]}})

        elif path == "/api/v1/ai/chat":
            chat = self._decode(body)
            chat["received_at"] = _now()
            chat["auth"] = bool(self.headers.get("Authorization"))
            _append_jsonl(CHAT_FILE, chat)
            self._json(200, {"response": "This is a canned reply from the collect-only test server."})

        else:
            match = re.fullmatch(r"/api/v1/captures/([0-9A-Fa-f-]+)/uploads/([0-9A-Fa-f-]+)/complete", path)
            if match:
                upload_id = match.group(2)
                print(f"+ upload complete {upload_id}")
                self._json(200, {"ok": True})
            elif (match := re.fullmatch(r"/api/v1/captures/([0-9A-Fa-f-]+)/uploads", path)):
                upload = self._decode(body)
                upload["received_at"] = _now()
                upload["upload_id"] = str(uuid.uuid4())
                upload["bytes_written"] = 0
                _append_jsonl(BASE / "uploads.jsonl", upload)
                print(f"+ upload session {upload['upload_id']} for {upload.get('filename')}")
                self._json(201, {"id": upload["upload_id"], "receivedBytes": 0})
            else:
                self._json(404, {"detail": "not found"})

    def do_PUT(self):
        UPLOADS.mkdir(parents=True, exist_ok=True)
        path = urlparse(self.path).path
        match = re.fullmatch(r"/api/v1/captures/([0-9A-Fa-f-]+)/uploads/([0-9A-Fa-f-]+)", path)
        if not match:
            self._json(404, {"detail": "not found"})
            return
        upload_id = match.group(2)
        data = self._read_body()
        target = UPLOADS / upload_id
        mode = "ab" if target.exists() else "wb"
        with target.open(mode) as f:
            f.write(data)
        print(f"+ upload chunk {upload_id}: {target.stat().st_size} bytes total")
        self.send_response(204)
        self.send_header("Upload-Offset", str(target.stat().st_size))
        self.end_headers()

    def _decode(self, body: bytes) -> dict:
        try:
            value = json.loads(body)
            return value if isinstance(value, dict) else {"raw": value}
        except json.JSONDecodeError:
            return {"raw_body": body.decode(errors="replace")}

    # ---------- inspect page ----------

    def _page(self):
        signals = _read_jsonl(INGEST_FILE)
        drafts = _read_jsonl(DRAFTS_FILE)
        chats = _read_jsonl(CHAT_FILE)
        rows = []
        for record in signals:
            payload = record.get("payload", {})
            data = payload.get("data", {})
            rows.append((record.get("client_timestamp", "?"), payload.get("type", "?"), payload.get("id", "?"), data))
        for draft in drafts:
            rows.append((draft.get("captured_at", "?"), "draft:" + str(draft.get("kind")), draft.get("capture_id", "?"), {k: v for k, v in draft.items() if k not in ("captured_at", "kind", "capture_id")}))
        rows.sort(key=lambda r: str(r[0]))
        html = ["<!doctype html><html><head><meta charset='utf-8'><title>LifeLog collect-only</title>",
                "<style>body{font-family:ui-monospace,Menlo,monospace;font-size:12px;margin:24px}"
                "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px;vertical-align:top;text-align:left}"
                "td{max-width:520px;overflow-wrap:anywhere}tr:nth-child(even){background:#f6f6f6}</style></head><body>",
                f"<h2>LifeLog collect-only server</h2>"
                f"<p>{len(signals)} signals | {len(drafts)} capture drafts | {len(chats)} chats | "
                f"uploaded files: {sum(1 for f in UPLOADS.iterdir())}</p>",
                "<table><tr><th>time</th><th>type</th><th>id</th><th>data</th></tr>"]
        for stamp, kind, sig_id, data in rows:
            html.append(f"<tr><td>{_html_escape(stamp)}</td><td>{_html_escape(kind)}</td>"
                        f"<td>{_html_escape(str(sig_id))}</td><td>{_html_escape(json.dumps(data, indent=1))}</td></tr>")
        html.append("</table></body></html>")
        self._send(200, "".join(html).encode(), "text/html; charset=utf-8")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    host = "0.0.0.0"
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"LifeLog collect-only server listening on http://{_lan_ip()}:{port}")
    print(f"Inspect collected data: http://{_lan_ip()}:{port}/inspect")
    print(f"Storage: {BASE}/")
    server.serve_forever()


if __name__ == "__main__":
    main()