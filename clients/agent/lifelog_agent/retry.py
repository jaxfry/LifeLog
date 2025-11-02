"""Retry logic with exponential backoff for network operations"""
from __future__ import annotations
import time
from typing import Optional


class RetryManager:
    """Manages retry attempts with exponential backoff for network operations"""
    
    def __init__(self, max_backoff: int = 300):
        """
        Initialize retry manager.
        
        Args:
            max_backoff: Maximum backoff time in seconds (default 5 minutes)
        """
        self.consecutive_failures = 0
        self.last_failure: Optional[float] = None
        self.max_backoff = max_backoff
    
    def backoff_seconds(self) -> int:
        """
        Calculate exponential backoff time.
        
        Returns:
            Seconds to wait: 1, 2, 4, 8, 16, 32, 64, 128, up to max_backoff
        """
        if self.consecutive_failures == 0:
            return 0
        
        # Exponential: 2^n, capped at max_backoff
        backoff = min(2 ** (self.consecutive_failures - 1), self.max_backoff)
        return int(backoff)
    
    def record_success(self):
        """Reset failure counter after successful operation"""
        if self.consecutive_failures > 0:
            # Log recovery
            self.consecutive_failures = 0
            self.last_failure = None
    
    def record_failure(self):
        """Increment failure counter after failed operation"""
        self.consecutive_failures += 1
        self.last_failure = time.time()
    
    def should_retry(self) -> bool:
        """
        Check if we should attempt another retry now.
        
        Returns:
            True if enough time has passed since last failure
        """
        if self.last_failure is None:
            return True
        
        elapsed = time.time() - self.last_failure
        return elapsed >= self.backoff_seconds()
    
    @property
    def is_failing(self) -> bool:
        """Check if currently in a failure state"""
        return self.consecutive_failures > 0
    
    @property
    def failure_count(self) -> int:
        """Get number of consecutive failures"""
        return self.consecutive_failures
