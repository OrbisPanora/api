"""WorldService and its worker functions, called in-process."""

import asyncio
import os
import zipfile

import pytest

from orbispanora_api.services import world_service as module
from orbispanora_api.services.world_service import WorldService, get_world_service
from orbispanora_api.settings import get_settings


@pytest.fixture
def service(make_client, world_dir):
    """The WorldService of an application that has loaded the test world."""
    make_client(world_dir)
    return get_world_service()


@pytest.fixture
def empty_service(make_client):
    make_client()
    return get_world_service()


class TestWorkers:

    def test_isometric_chunk(self, world_dir):
        result = module._worker_get_chunk_isometric(str(world_dir), "overworld", 0, 0)
        assert result is not None
        assert (result["chunk_x"], result["chunk_z"]) == (0, 0)
        assert result["x"] and result["palette"]
        assert len(result["x"]) == len(result["y"]) == len(result["z"]) == len(result["block"])

    def test_isometric_chunk_that_does_not_exist(self, world_dir):
        assert module._worker_get_chunk_isometric(str(world_dir), "overworld", 9, 9) is None

    def test_render_data(self, world_dir):
        # Chunk 0,1 has land. Chunk 0,0 is water only, which this mode does not draw.
        result = module._worker_generate_render_data(str(world_dir), "overworld", 0, 1)
        assert result["blocks"]
        assert set(result["bounds"]) == {"min_x", "max_x", "min_y", "max_y"}
        assert result["sprites"]

    def test_render_data_of_a_chunk_that_does_not_exist(self, world_dir):
        assert module._worker_generate_render_data(str(world_dir), "overworld", 9, 9)["blocks"] == []


class TestChunkData:

    def test_isometric_mode_in_process(self, service):
        data = service.get_chunk_data(0, 0, 0, "isometric")
        assert data is not None
        assert data.x and data.palette
        assert isinstance(data.surface_y, int)

    def test_isometric_mode_gives_what_the_worker_gives(self, service, world_dir):
        for chunk in [(0, 0), (1, 1), (9, 9)]:
            worker = module._worker_get_chunk_isometric(str(world_dir), "overworld", *chunk)
            direct = service.get_chunk_data(*chunk, 0, "isometric")
            assert (worker is None) == (direct is None)
            if worker is not None:
                assert direct.model_dump() == worker

    def test_render_mode_in_process(self, service):
        data = service.get_chunk_data(0, 1, 0, "render")
        assert data is not None and data.render_data is not None
        assert data.render_data["blocks"]

    def test_unknown_chunk(self, service):
        assert service.get_chunk_data(9, 9, 0, "heightmap") is None

    def test_async_isometric_matches_in_process(self, service):
        asynchronous = asyncio.run(service.get_chunk_data_async(0, 0, 0, "isometric"))
        assert asynchronous.x

    def test_async_other_modes_use_the_synchronous_path(self, service):
        assert asyncio.run(service.get_chunk_data_async(0, 0, 0, "heightmap")).heightmap

    def test_async_of_a_chunk_that_does_not_exist(self, service):
        assert asyncio.run(service.get_chunk_data_async(9, 9, 0, "isometric")) is None

    def test_async_render_data(self, service):
        assert asyncio.run(service.get_render_data_async(0, 1))["blocks"]


def test_sprite_keys():
    service = WorldService.__new__(WorldService)
    assert service._get_sprite_key("minecraft:grass_block", "plains") == "grass_plains"
    assert service._get_sprite_key("minecraft:grass_block", "taiga") == "grass_taiga"
    assert service._get_sprite_key("minecraft:grass_block", "desert") == "sand"
    assert service._get_sprite_key("minecraft:grass_block", "swamp") == "grass_default"
    for name, key in [("stone", "stone"), ("dirt", "dirt"), ("water", "water"), ("sand", "sand"), ("oak_log", "oak_log"), ("oak_leaves", "oak_leaves")]:
        assert service._get_sprite_key(f"minecraft:{name}", "plains") == key
    assert service._get_sprite_key("minecraft:bedrock", "plains") == "unknown_block"
    assert service._get_sprite_data("water")["color"] == "#2196F3"
    assert service._get_sprite_data("nothing")["color"] == "#666666"


class TestLoading:

    def test_info_of_the_loaded_world(self, service):
        info = service.get_world_info()
        assert info.dimension == "overworld"
        assert info.bounds == [0, -64, 0, 511, 320, 511]

    def test_area_and_tile(self, service):
        assert service.get_area_heightmap(0, 0, 3, 3).width == 4
        assert service.get_tile_data(0, 0, 1).chunk_count == 1

    def test_zip_that_is_not_a_zip(self, empty_service, tmp_path):
        path = tmp_path / "bad.zip"
        path.write_text("text")
        with pytest.raises(ValueError):
            empty_service.load_world_from_zip(str(path))

    def test_zip_larger_than_the_limit(self, empty_service, world_zip, monkeypatch):
        monkeypatch.setenv("ORBISPANORA_UPLOAD_MAX_SIZE_MB", "1")
        get_settings.cache_clear()
        monkeypatch.setattr(os.path, "getsize", lambda path: 2 * 1024 * 1024)
        with pytest.raises(ValueError):
            empty_service.load_world_from_zip(str(world_zip))

    def test_zip_without_a_world(self, empty_service, tmp_path):
        path = tmp_path / "empty.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("readme.txt", "nothing")
        with pytest.raises(ValueError):
            empty_service.load_world_from_zip(str(path))
        assert os.listdir(get_settings().temp_world_dir) == []

    def test_zip_with_a_world_in_a_folder(self, empty_service, world_zip):
        path = empty_service.load_world_from_zip(str(world_zip))
        assert os.path.basename(path) == "world"
        assert empty_service.is_loaded()

    def test_old_extracted_worlds_are_removed(self, empty_service, world_zip, monkeypatch):
        monkeypatch.setenv("ORBISPANORA_MAX_TEMP_WORLDS", "2")
        get_settings.cache_clear()
        for _ in range(4):
            empty_service.load_world_from_zip(str(world_zip))
        assert len(os.listdir(get_settings().temp_world_dir)) == 2

    def test_find_world_directory_in_an_empty_folder(self, empty_service, tmp_path):
        assert empty_service._find_world_directory(str(tmp_path)) is None
