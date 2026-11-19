"""
Cache service with Redis and in-memory support.
Handles caching for heightmaps, surface blocks, and chunks.
"""

import json
import time
from typing import Optional, Any, Dict
from abc import ABC, abstractmethod
import hashlib


class CacheBackend(ABC):
    """Abstract base class for cache backends."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        pass
    
    @abstractmethod
    async def clear(self) -> None:
        """Clear all cache."""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass


class MemoryCacheBackend(CacheBackend):
    """In-memory cache backend for development."""
    
    def __init__(self):
        self._cache: Dict[str, tuple[Any, float]] = {}
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self._cache:
            value, expiry = self._cache[key]
            if expiry > time.time():
                return value
            else:
                # Expired, remove it
                del self._cache[key]
        return None
    
    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL."""
        expiry = time.time() + ttl
        self._cache[key] = (value, expiry)
    
    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        if key in self._cache:
            del self._cache[key]
    
    async def clear(self) -> None:
        """Clear all cache."""
        self._cache.clear()
    
    async def exists(self, key: str) -> bool:
        """Check if key exists and not expired."""
        if key in self._cache:
            _, expiry = self._cache[key]
            if expiry > time.time():
                return True
            else:
                del self._cache[key]
        return False
    
    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns number of removed entries."""
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if expiry <= current_time
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)


class RedisCacheBackend(CacheBackend):
    """Redis cache backend for production."""
    
    def __init__(self, redis_url: str):
        try:
            import redis.asyncio as redis
            self.redis = redis.from_url(redis_url, decode_responses=True)
        except ImportError:
            raise ImportError("redis package is required for Redis cache. Install with: pip install redis")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        value = await self.redis.get(key)
        if value:
            return json.loads(value)
        return None
    
    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL."""
        await self.redis.setex(key, ttl, json.dumps(value))
    
    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        await self.redis.delete(key)
    
    async def clear(self) -> None:
        """Clear all cache."""
        await self.redis.flushdb()
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        return await self.redis.exists(key) > 0


class CacheService:
    """
    Cache service for OrbisPanora API.
    Handles caching with different TTLs for different data types.
    """
    
    def __init__(self, backend: CacheBackend, ttl_config: Dict[str, int]):
        self.backend = backend
        self.ttl_config = ttl_config
        self._enabled = True
    
    def _make_key(self, prefix: str, *args) -> str:
        """Generate cache key from prefix and arguments."""
        # Create a hash of the arguments for consistent keys
        key_parts = [str(arg) for arg in args]
        key_string = ":".join([prefix] + key_parts)
        return key_string
    
    async def get_heightmap(self, x: int, z: int, radius: int) -> Optional[Any]:
        """Get heightmap from cache."""
        if not self._enabled:
            return None
        key = self._make_key("heightmap", x, z, radius)
        return await self.backend.get(key)
    
    async def set_heightmap(self, x: int, z: int, radius: int, data: Any) -> None:
        """Cache heightmap data."""
        if not self._enabled:
            return
        key = self._make_key("heightmap", x, z, radius)
        ttl = self.ttl_config.get("heightmap", 300)
        await self.backend.set(key, data, ttl)
    
    async def get_surface_blocks(self, x: int, z: int, radius: int) -> Optional[Any]:
        """Get surface blocks from cache."""
        if not self._enabled:
            return None
        key = self._make_key("surface", x, z, radius)
        return await self.backend.get(key)
    
    async def set_surface_blocks(self, x: int, z: int, radius: int, data: Any) -> None:
        """Cache surface blocks data."""
        if not self._enabled:
            return
        key = self._make_key("surface", x, z, radius)
        ttl = self.ttl_config.get("surface", 120)
        await self.backend.set(key, data, ttl)
    
    async def get_chunk(self, chunk_x: int, chunk_z: int) -> Optional[Any]:
        """Get chunk from cache."""
        if not self._enabled:
            return None
        key = self._make_key("chunk", chunk_x, chunk_z)
        return await self.backend.get(key)
    
    async def set_chunk(self, chunk_x: int, chunk_z: int, data: Any) -> None:
        """Cache chunk data."""
        if not self._enabled:
            return
        key = self._make_key("chunk", chunk_x, chunk_z)
        ttl = self.ttl_config.get("chunk", 600)
        await self.backend.set(key, data, ttl)
    
    async def invalidate_chunk(self, chunk_x: int, chunk_z: int) -> None:
        """Invalidate chunk cache (on modification)."""
        key = self._make_key("chunk", chunk_x, chunk_z)
        await self.backend.delete(key)
    
    async def invalidate_area(self, x: int, z: int, radius: int) -> None:
        """Invalidate all caches for an area (on modification)."""
        # Invalidate heightmap
        heightmap_key = self._make_key("heightmap", x, z, radius)
        await self.backend.delete(heightmap_key)
        
        # Invalidate surface blocks
        surface_key = self._make_key("surface", x, z, radius)
        await self.backend.delete(surface_key)
        
        # Invalidate affected chunks
        chunk_x_start = (x - radius) >> 4
        chunk_z_start = (z - radius) >> 4
        chunk_x_end = (x + radius) >> 4
        chunk_z_end = (z + radius) >> 4
        
        for cx in range(chunk_x_start, chunk_x_end + 1):
            for cz in range(chunk_z_start, chunk_z_end + 1):
                await self.invalidate_chunk(cx, cz)
    
    async def clear_all(self) -> None:
        """Clear all cache."""
        await self.backend.clear()
    
    def enable(self) -> None:
        """Enable caching."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable caching."""
        self._enabled = False
    
    @property
    def is_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._enabled


# Global cache service instance
_cache_service: Optional[CacheService] = None


def init_cache_service(cache_type: str, redis_url: str, ttl_config: Dict[str, int]) -> CacheService:
    """Initialize the cache service."""
    global _cache_service
    
    if cache_type == "redis":
        backend = RedisCacheBackend(redis_url)
    else:
        backend = MemoryCacheBackend()
    
    _cache_service = CacheService(backend, ttl_config)
    return _cache_service


def get_cache_service() -> Optional[CacheService]:
    """Get the global cache service instance."""
    return _cache_service
