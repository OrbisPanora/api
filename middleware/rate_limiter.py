"""
Rate limiting middleware to prevent API abuse.
"""

import time
from typing import Dict, Tuple
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
import asyncio


class RateLimiter:
    """
    Rate limiter using sliding window algorithm.
    Tracks requests per IP address.
    """
    
    def __init__(self, requests: int, window: int):
        """
        Initialize rate limiter.
        
        Parameters
        ----------
        requests : int
            Maximum number of requests allowed per window
        window : int
            Time window in seconds
        """
        self.max_requests = requests
        self.window = window
        self._requests: Dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, client_ip: str) -> Tuple[bool, int]:
        """
        Check if request is allowed for the client IP.
        
        Parameters
        ----------
        client_ip : str
            Client IP address
        
        Returns
        -------
        Tuple[bool, int]
            (is_allowed, remaining_requests)
        """
        async with self._lock:
            current_time = time.time()
            window_start = current_time - self.window
            
            # Get requests for this IP
            requests = self._requests[client_ip]
            
            # Remove old requests outside the window
            requests[:] = [req_time for req_time in requests if req_time > window_start]
            
            # Check if limit exceeded
            if len(requests) >= self.max_requests:
                return False, 0
            
            # Add current request
            requests.append(current_time)
            
            remaining = self.max_requests - len(requests)
            return True, remaining
    
    async def cleanup_old_entries(self):
        """Remove old entries to prevent memory leak."""
        async with self._lock:
            current_time = time.time()
            window_start = current_time - self.window
            
            # Remove IPs with no recent requests
            ips_to_remove = []
            for ip, requests in self._requests.items():
                requests[:] = [req_time for req_time in requests if req_time > window_start]
                if not requests:
                    ips_to_remove.append(ip)
            
            for ip in ips_to_remove:
                del self._requests[ip]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.
    """
    
    def __init__(self, app, *, requests: int, window: int, enabled: bool = True):
        super().__init__(app)
        self.rate_limiter = RateLimiter(requests, window)
        self.enabled = enabled
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        if not self.enabled:
            return await call_next(request)
        
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Check rate limit
        allowed, remaining = await self.rate_limiter.is_allowed(client_ip)
        
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={
                    "X-RateLimit-Limit": str(self.rate_limiter.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + self.rate_limiter.window))
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.rate_limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + self.rate_limiter.window))
        
        return response
