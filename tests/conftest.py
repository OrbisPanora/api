"""Fixtures: the application in-process, with a small generated world or with none."""

import os

import pytest
from fastapi.testclient import TestClient

from orbispanora_api.settings import get_settings
from tests.utilities.make_world import build_world, build_world_zip

# Middleware is configured when `orbispanora_api.main` is imported, so these are set first.
os.environ["ORBISPANORA_CACHE_ENABLED"] = "false"
os.environ["ORBISPANORA_RATE_LIMIT_ENABLED"] = "false"
os.environ["ORBISPANORA_COMPRESSION_ENABLED"] = "false"


def _reset_services():
    """Forget the world and the worker processes of the previous test."""
    from orbispanora_api.services import world_service  # pylint: disable=import-outside-toplevel

    if world_service._world_service is not None:  # pylint: disable=protected-access
        world_service._world_service.shutdown()  # pylint: disable=protected-access
    world_service._world_service = None  # pylint: disable=protected-access
    world_service.WorldService._instance = None  # pylint: disable=protected-access
    world_service.WorldService._world = None  # pylint: disable=protected-access
    world_service.WorldService._world_path = None  # pylint: disable=protected-access


@pytest.fixture
def world_dir(tmp_path):
    """A world folder with four chunks."""
    return build_world(tmp_path / "world")


@pytest.fixture
def world_zip(tmp_path):
    """A zip file holding a world folder."""
    return build_world_zip(tmp_path / "world.zip")


@pytest.fixture
def make_client(monkeypatch, tmp_path):
    """Build a test client, with or without a world, and clean up afterwards."""
    clients = []

    def make(world_path=None):
        monkeypatch.delenv("ORBISPANORA_WORLD_PATH", raising=False)
        if world_path is not None:
            monkeypatch.setenv("ORBISPANORA_WORLD_PATH", str(world_path))
        monkeypatch.setenv("ORBISPANORA_TEMP_WORLD_DIR", str(tmp_path / "worlds"))
        monkeypatch.setenv("ORBISPANORA_UPLOAD_CHUNKS_DIR", str(tmp_path / "chunks"))
        get_settings.cache_clear()
        _reset_services()
        from orbispanora_api.main import app  # pylint: disable=import-outside-toplevel

        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)
    _reset_services()
    get_settings.cache_clear()


@pytest.fixture
def client(make_client, world_dir):
    """A client for an API with a world loaded."""
    return make_client(world_dir)


@pytest.fixture
def client_without_world(make_client):
    """A client for an API that has no world."""
    return make_client()
