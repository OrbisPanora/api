"""The pool of worker processes and the world each worker keeps open."""

import shutil

import pytest
from orbispanora_lib.anvil import Region

from orbispanora_api.routers.isometric import get_isometric_service
from orbispanora_api.services import world_service as module
from orbispanora_api.services.world_service import get_world_service
from orbispanora_api.settings import get_settings
from tests.utilities.make_world import build_world


@pytest.fixture
def service(make_client, world_dir):
    """The WorldService of an application that has loaded the test world."""
    make_client(world_dir)
    return get_world_service()


@pytest.fixture(autouse=True)
def fresh_worker_state():
    """Each test starts with no world open in this process."""
    module._worker_state = None  # pylint: disable=protected-access
    yield
    module._worker_state = None  # pylint: disable=protected-access


def test_the_pool_has_the_size_of_the_setting(make_client, world_dir, monkeypatch):
    monkeypatch.setenv("ORBISPANORA_WORKERS", "2")
    make_client(world_dir)
    assert getattr(get_world_service().executor, "_max_workers") == 2  # pylint: disable=literal-comparison


def test_the_chunk_route_and_the_isometric_routes_share_one_pool(service):
    assert get_isometric_service().executor is service.executor


def test_loading_another_world_replaces_the_workers_and_stops_the_old_ones(service, tmp_path):
    before = service.executor
    other = build_world(tmp_path / "other")
    service.load_world_from_path(str(other))
    assert service.executor is not before
    assert before._shutdown_thread  # pylint: disable=protected-access


def test_the_old_world_is_closed_when_another_one_is_loaded(service, tmp_path):
    old = service.world
    assert old.get_chunk(0, 0) is not None and old.regions
    service.load_world_from_path(str(build_world(tmp_path / "other")))
    assert not old.regions


def test_a_worker_keeps_one_world_and_reports_when_it_opened_it(world_dir, tmp_path):
    other = build_world(tmp_path / "other")
    first, cold = module.worker_world(str(world_dir), "overworld")
    assert cold
    again, cold = module.worker_world(str(world_dir), "overworld")
    assert again is first and not cold
    second, cold = module.worker_world(str(other), "overworld")
    assert cold and second is not first
    assert not first.regions, "the previous world was closed"
    _, cold = module.worker_world(str(world_dir), "overworld")
    assert cold, "the first world was released, so it is opened again"


def test_a_worker_keeps_one_world_per_dimension(world_dir):
    shutil.copytree(world_dir / "region", world_dir / "DIM-1" / "region")
    first, _ = module.worker_world(str(world_dir), "overworld")
    nether, cold = module.worker_world(str(world_dir), "nether")
    assert cold and nether is not first and not first.regions


def test_the_caches_of_a_world_have_the_sizes_of_the_settings(world_dir, monkeypatch):
    monkeypatch.setenv("ORBISPANORA_WORLD_CHUNK_CACHE", "5")
    monkeypatch.setenv("ORBISPANORA_WORLD_REGION_CACHE", "2")
    get_settings.cache_clear()
    world, _ = module.worker_world(str(world_dir), "overworld")
    chunk_cache = world._chunk_cache  # pylint: disable=protected-access
    region_cache = world._region_cache  # pylint: disable=protected-access
    assert chunk_cache is not None and region_cache is not None
    assert (chunk_cache.max_size, region_cache.max_size) == (5, 2)


def test_the_worker_does_not_hold_the_region_file(world_dir):
    module._worker_get_chunk_isometric(str(world_dir), "overworld", 0, 0)  # pylint: disable=protected-access
    state = module._worker_state  # pylint: disable=protected-access
    assert state is not None
    region = state[1].regions[(0, 0)]
    assert isinstance(region, Region) and type(region.data).__name__ == "FileBytes"
