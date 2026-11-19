"""Chunk, area, tile and viewport endpoints."""

import pytest


@pytest.mark.parametrize("mode", ["heightmap", "surface", "isometric", "render", "simplified", "full"])
def test_chunk_modes(client, mode):
    response = client.get("/api/chunks/0/0/0", params={"mode": mode})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
    assert response.json()["data"]["chunk_x"] == 0


def test_heightmap_mode_has_only_the_heightmap(client):
    data = client.get("/api/chunks/0/0/0", params={"mode": "heightmap"}).json()["data"]
    assert len(data["heightmap"]) == 16
    assert data["heightmap"][0][0] == 62
    assert data["surface_blocks"] is None


def test_surface_mode_lists_blocks_with_biomes(client):
    data = client.get("/api/chunks/0/0/0", params={"mode": "surface"}).json()["data"]
    assert data["surface_blocks"][0] == {"x": 0, "y": 62, "z": 0, "block": "minecraft:water", "biome": "minecraft:river"}


def test_unknown_mode_is_rejected(client):
    assert client.get("/api/chunks/0/0/0", params={"mode": "bad"}).status_code == 422


def test_missing_chunk_is_not_found(client):
    assert client.get("/api/chunks/9/9/0").status_code == 404


def test_chunk_without_a_world(client_without_world):
    assert client_without_world.get("/api/chunks/0/0/0", params={"mode": "heightmap"}).status_code == 503


def test_area_heightmap(client):
    data = client.get("/api/chunks/area/heightmap", params={"x1": 0, "z1": 0, "x2": 20, "z2": 20}).json()["data"]
    assert (data["width"], data["height"]) == (21, 21)
    assert data["heightmap"][0][0] == 62


def test_area_heightmap_without_a_world(client_without_world):
    response = client_without_world.get("/api/chunks/area/heightmap", params={"x1": 0, "z1": 0, "x2": 5, "z2": 5})
    assert response.status_code == 503


def test_tile_route_is_not_taken_by_the_chunk_route(client):
    response = client.get("/api/chunks/tile/0/0", params={"size": 1})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["tile_size"] == 1
    assert data["chunk_count"] == 1


@pytest.mark.parametrize("size", [0, 33])
def test_tile_size_limits(client, size):
    assert client.get("/api/chunks/tile/0/0", params={"size": size}).status_code == 422


def test_tile_without_a_world(client_without_world):
    assert client_without_world.get("/api/chunks/tile/0/0", params={"size": 1}).status_code == 503


def test_viewport_render(client):
    response = client.get("/api/chunks/viewport/render", params={"center_x": 0, "center_z": 0, "view_distance": 1})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["center_chunk"] == {"x": 0, "z": 0}
    assert data["view_distance"] == 1


def test_viewport_render_without_a_world_is_unavailable(client_without_world):
    response = client_without_world.get("/api/chunks/viewport/render", params={"center_x": 0, "center_z": 0, "view_distance": 1})
    assert response.status_code == 503


def test_viewport_render_lists_the_chunks_with_blocks(client):
    data = client.get("/api/chunks/viewport/render", params={"center_x": 0, "center_z": 0, "view_distance": 1}).json()["data"]
    assert data["stats"]["total_chunks"] == len(data["chunks"]) > 0
    assert data["stats"]["total_blocks"] > 0
    assert data["sprites"]
