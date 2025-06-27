"""
LifeLog Local Daemon Package.

This package contains the components for the local daemon responsible for
collecting user activity, caching it, and sending it to a central server.
"""
import logging

# Configure a basic null handler for the package logger.
# Applications using this package should configure their own logging.
# This prevents "No handler found" warnings if the package is used
# without explicit logging configuration by the application.
logging.getLogger(__name__).addHandler(logging.NullHandler())

# You can make key components available for easier import if desired, e.g.:
# from .daemon import main as run_daemon
# from .collector import ActivityWatchCollector
# from .sender import attempt_send_cached_data
# from .cache import initialize_cache

VERSION = "0.1.0" # Initial version
