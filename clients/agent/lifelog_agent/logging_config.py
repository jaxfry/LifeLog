"""Logging configuration for LifeLog Agent"""
from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .config import CONFIG_DIR


def setup_logging(verbose: bool = False) -> logging.Logger:
    """
    Set up logging with rotation and both file + console handlers.
    
    Args:
        verbose: If True, set console to DEBUG level
        
    Returns:
        Logger instance
    """
    # Ensure log directory exists
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = CONFIG_DIR / "agent.log"
    
    # Create logger
    logger = logging.getLogger("lifelog.agent")
    logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # File handler with rotation (10MB max, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def get_logger() -> logging.Logger:
    """Get the agent logger instance"""
    return logging.getLogger("lifelog.agent")
