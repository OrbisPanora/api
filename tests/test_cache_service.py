"""The cache service, with the in-memory backend and a stand-in for Redis."""

import asyncio
import sys
import types

import pytest

from orbispanora_api.services import cache_service
from orbispanora_api.services.cache_service import (
    CacheService,
    MemoryCacheBackend,
    RedisCacheBackend,
)


def run(coroutine):
    return asyncio.run(coroutine)


class TestMemoryBackend:

    def test_set_get_exists_delete(self):
        backend = MemoryCacheBackend()
        run(backend.set("a", {"x": 1}, 60))
        assert run(backend.get("a")) == {"x": 1}
        assert run(backend.exists("a")) is True
        run(backend.delete("a"))
        run(backend.delete("a"))
        assert run(backend.get("a")) is None
        assert run(backend.exists("a")) is False

    def test_expired_entries_are_dropped(self):
        backend = MemoryCacheBackend()
        run(backend.set("a", 1, -1))
        run(backend.set("b", 2, -1))
        run(backend.set("c", 3, 60))
        assert run(backend.exists("a")) is False
        assert run(backend.get("b")) is None
        assert backend.cleanup_expired() == 0
        run(backend.set("d", 4, -1))
        assert backend.cleanup_expired() == 1

    def test_clear(self):
        backend = MemoryCacheBackend()
        run(backend.set("a", 1, 60))
        run(backend.clear())
        assert run(backend.get("a")) is None


class TestService:

    @staticmethod
    def service():
        return CacheService(MemoryCacheBackend(), {"heightmap": 10, "surface": 10, "chunk": 10})

    def test_each_kind_of_data_round_trips(self):
        service = self.service()
        run(service.set_heightmap(0, 0, 2, [1]))
        run(service.set_surface_blocks(0, 0, 2, [2]))
        run(service.set_chunk(1, 1, [3]))
        assert run(service.get_heightmap(0, 0, 2)) == [1]
        assert run(service.get_surface_blocks(0, 0, 2)) == [2]
        assert run(service.get_chunk(1, 1)) == [3]

    def test_invalidate_area_removes_the_chunks_it_covers(self):
        service = self.service()
        run(service.set_chunk(0, 0, "a"))
        run(service.set_chunk(5, 5, "b"))
        run(service.set_heightmap(8, 8, 4, "h"))
        run(service.invalidate_area(8, 8, 4))
        assert run(service.get_chunk(0, 0)) is None
        assert run(service.get_heightmap(8, 8, 4)) is None
        assert run(service.get_chunk(5, 5)) == "b"

    def test_invalidate_chunk_and_clear_all(self):
        service = self.service()
        run(service.set_chunk(0, 0, "a"))
        run(service.set_chunk(1, 0, "b"))
        run(service.invalidate_chunk(0, 0))
        assert run(service.get_chunk(0, 0)) is None
        run(service.clear_all())
        assert run(service.get_chunk(1, 0)) is None

    def test_disabled_service_stores_and_returns_nothing(self):
        service = self.service()
        service.disable()
        assert service.is_enabled is False
        run(service.set_heightmap(0, 0, 1, "h"))
        run(service.set_surface_blocks(0, 0, 1, "s"))
        run(service.set_chunk(0, 0, "c"))
        assert run(service.get_heightmap(0, 0, 1)) is None
        assert run(service.get_surface_blocks(0, 0, 1)) is None
        assert run(service.get_chunk(0, 0)) is None
        service.enable()
        assert run(service.get_chunk(0, 0)) is None


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def setex(self, key, ttl, value):
        self.data[key] = value

    async def delete(self, key):
        self.data.pop(key, None)

    async def flushdb(self):
        self.data.clear()

    async def exists(self, key):
        return int(key in self.data)


@pytest.fixture
def fake_redis(monkeypatch):
    module = types.SimpleNamespace(from_url=lambda url, decode_responses: FakeRedis())
    package = types.SimpleNamespace(asyncio=module)
    monkeypatch.setitem(sys.modules, "redis", package)
    monkeypatch.setitem(sys.modules, "redis.asyncio", module)


class TestRedisBackend:

    def test_set_get_exists_delete_clear(self, fake_redis):
        backend = RedisCacheBackend("redis://example.invalid")
        run(backend.set("a", {"x": 1}, 60))
        assert run(backend.get("a")) == {"x": 1}
        assert run(backend.exists("a")) is True
        run(backend.delete("a"))
        assert run(backend.get("a")) is None
        run(backend.set("b", 1, 60))
        run(backend.clear())
        assert run(backend.exists("b")) is False

    def test_missing_package(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "redis", None)
        monkeypatch.setitem(sys.modules, "redis.asyncio", None)
        with pytest.raises(ImportError):
            RedisCacheBackend("redis://example.invalid")


def test_init_selects_the_backend(fake_redis):
    assert isinstance(cache_service.init_cache_service("memory", "", {}).backend, MemoryCacheBackend)
    assert cache_service.get_cache_service() is not None
    assert isinstance(cache_service.init_cache_service("redis", "redis://example.invalid", {}).backend, RedisCacheBackend)
