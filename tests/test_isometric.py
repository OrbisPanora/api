"""Isometric endpoints, their worker functions and the visibility rules."""

import pytest

from orbispanora_api.routers import isometric
from orbispanora_api.routers.isometric import BlockData
from orbispanora_api.services.world_service import get_world_service


def block(x, y, z, name="minecraft:stone"):
    return BlockData(x, y, z, name, "minecraft:plains")


class TestTransparency:

    @pytest.mark.parametrize("name", ["minecraft:glass", "minecraft:oak_leaves", "minecraft:pink_tulip_flower", "", None])
    def test_transparent(self, name):
        assert isometric.is_transparent(name)

    @pytest.mark.parametrize("name", ["minecraft:stone", "minecraft:dirt"])
    def test_opaque(self, name):
        assert not isometric.is_transparent(name)


class TestCulling:

    def test_no_blocks(self):
        assert isometric._apply_global_culling([]) == []

    @staticmethod
    def solid_square():
        """Columns at x and z in 0..1, y 60..69, so that every face towards +X, +Y, +Z of (0, y, 0) has a block."""
        return [block(x, y, z) for x in range(2) for z in range(2) for y in range(60, 70)]

    def test_buried_blocks_below_the_surface_depth_are_dropped(self):
        kept = {(b.x, b.y, b.z) for b in isometric._apply_global_culling(self.solid_square())}
        assert (0, 69, 0) in kept and (0, 66, 0) in kept
        assert (0, 65, 0) not in kept and (0, 60, 0) not in kept

    def test_deeper_block_with_an_exposed_face_is_kept(self):
        kept = {(b.x, b.y, b.z) for b in isometric._apply_global_culling(self.solid_square())}
        # The face towards +X of (1, 60, 0) has no block next to it.
        assert (1, 60, 0) in kept

    def test_transparent_blocks_are_always_kept(self):
        kept = isometric._apply_global_culling([block(0, 10, 0, "minecraft:water"), block(0, 20, 0)])
        assert len(kept) == 2


class TestWorkers:

    def test_all_blocks_in_a_range(self, world_dir):
        data = isometric._worker_extract_all_blocks(str(world_dir), "overworld", 0, 0, 60, 62)
        assert (data.chunk_x, data.chunk_z) == (0, 0)
        assert data.bounds == (0, 15, 0, 15)
        assert {b.y for b in data.blocks} == {60, 61, 62}
        assert "minecraft:water" in {b.block for b in data.blocks}

    def test_all_blocks_of_a_missing_chunk(self, world_dir):
        assert isometric._worker_extract_all_blocks(str(world_dir), "overworld", 9, 9, 60, 62).blocks == []

    def test_all_blocks_of_a_missing_world(self, tmp_path):
        assert isometric._worker_extract_all_blocks(str(tmp_path / "absent"), "overworld", 0, 0, 60, 62).blocks == []

    def test_surface_blocks(self, world_dir):
        blocks = isometric._worker_extract_surface_blocks(str(world_dir), "overworld", 0, 0)
        assert blocks
        assert all(isinstance(b, BlockData) for b in blocks)

    def test_surface_blocks_of_a_missing_chunk(self, world_dir):
        assert isometric._worker_extract_surface_blocks(str(world_dir), "overworld", 9, 9) == []

    def test_surface_blocks_of_a_missing_world(self, tmp_path):
        assert isometric._worker_extract_surface_blocks(str(tmp_path / "absent"), "overworld", 0, 0) == []


class TestBlocksEndpoint:

    def test_radius_zero_is_one_chunk(self, client):
        data = client.get("/api/isometric/blocks", params={"radius": 0, "min_y": 60, "max_y": 62}).json()["data"]
        assert data["chunks_loaded"] == 1
        assert data["selection"] == {"mode": "radius", "requested_chunks": 1, "processed_chunks": 1, "limit_applied": False}
        assert data["bounds"]["min_y"] == 60

    def test_list_mode_and_cache(self, client):
        params = {"mode": "list", "chunk_list": "0,0;1,0", "min_y": 61, "max_y": 62}
        first = client.get("/api/isometric/blocks", params=params).json()["data"]
        second = client.get("/api/isometric/blocks", params=params).json()["data"]
        assert first["chunks_loaded"] == 2
        assert second["cache_hit_rate"] != "0%"
        assert client.get("/api/isometric/stats").json()["data"]["cache_hits"] >= 2

    def test_all_mode_with_a_limit(self, client):
        data = client.get("/api/isometric/blocks", params={"mode": "all", "limit": 1, "min_y": 62, "max_y": 62}).json()["data"]
        assert data["selection"]["limit_applied"] is True
        assert data["selection"]["processed_chunks"] == 1

    def test_missing_chunks_give_an_empty_result(self, client):
        data = client.get("/api/isometric/blocks", params={"mode": "list", "chunk_list": "9,9"}).json()["data"]
        assert data["total_blocks"] == 0

    def test_limit_zero_gives_an_empty_result(self, client):
        assert client.get("/api/isometric/blocks", params={"limit": 0}).json()["data"]["total_blocks"] == 0

    @pytest.mark.parametrize("params", [{"mode": "list"}, {"mode": "list", "chunk_list": "a,b"}, {"mode": "sideways"}])
    def test_bad_requests(self, client, params):
        assert client.get("/api/isometric/blocks", params=params).status_code == 400

    def test_radius_is_limited(self, client):
        assert client.get("/api/isometric/blocks", params={"radius": 17}).status_code == 422

    def test_without_a_world(self, client_without_world):
        assert client_without_world.get("/api/isometric/blocks").status_code == 503


class TestSurfaceEndpoint:

    def test_radius_zero(self, client):
        data = client.get("/api/isometric/surface", params={"radius": 0}).json()["data"]
        assert data["chunks_loaded"] == 1
        assert data["total_blocks"] > 0
        assert data["bounds"]["min_x"] == 0

    def test_list_mode_ignores_malformed_pairs(self, client):
        data = client.get("/api/isometric/surface", params={"mode": "list", "chunk_list": "0,0;x,y"}).json()["data"]
        assert data["chunks_loaded"] == 1

    def test_all_mode_with_a_limit(self, client):
        data = client.get("/api/isometric/surface", params={"mode": "all", "limit": 1}).json()["data"]
        assert data["selection"]["limit_applied"] is True

    def test_missing_chunk_list(self, client):
        assert client.get("/api/isometric/surface", params={"mode": "list"}).status_code == 400

    def test_without_a_world(self, client_without_world):
        assert client_without_world.get("/api/isometric/surface").status_code == 503


def test_clear_cache_empties_the_cache(client):
    client.get("/api/isometric/blocks", params={"radius": 0, "min_y": 62, "max_y": 62})
    assert client.post("/api/isometric/cache/clear").json()["data"]["message"] == "Cache cleared"
    again = client.get("/api/isometric/blocks", params={"radius": 0, "min_y": 62, "max_y": 62}).json()["data"]
    assert again["chunks_loaded"] == 1


def test_scan_all_regions_ignores_other_files(client, world_dir):
    (world_dir / "region" / "r.x.y.mca").write_bytes(b"")
    (world_dir / "region" / "notes.txt").write_text("")
    service = isometric.get_isometric_service()
    assert len(service.scan_all_regions(get_world_service())) == 1024
