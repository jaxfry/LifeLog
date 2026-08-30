# This file is added to PYTHONPATH for isolated actor processes.
# It disables network access when LIFELOG_NO_NETWORK=1.
import os

if os.environ.get('LIFELOG_NO_NETWORK') == '1':
    try:
        import socket
        _orig_create_conn = socket.create_connection
        _orig_socket = socket.socket

        def _deny(*args, **kwargs):
            raise RuntimeError("Network access is disabled for this extension")

        socket.create_connection = _deny  # type: ignore

        class _NoNetSocket(socket.socket):  # type: ignore
            def connect(self, *args, **kwargs):
                raise RuntimeError("Network access is disabled for this extension")

        socket.socket = _NoNetSocket  # type: ignore
    except Exception:
        pass
