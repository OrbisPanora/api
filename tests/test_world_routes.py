"""World, block and biome endpoints, with a world and without one."""

import pytest


def test_root_lists_the_resources(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_health_with_a_world(client):
    data = client.get("/api/worlds/health").json()
    assert data["status"] == "healthy"
    assert data["world_loaded"] is True


def test_health_without_a_world(client_without_world):
    data = client_without_world.get("/api/worlds/health").json()
    assert data["status"] == "unhealthy"
    assert data["world_loaded"] is False


def test_current_world(client):
    response = client.get("/api/worlds/current")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["dimension"] == "overworld"
    assert data["bounds"] == [0, -64, 0, 511, 320, 511]


def test_current_world_without_a_world(client_without_world):
    assert client_without_world.get("/api/worlds/current").status_code == 503


def test_switch_dimension(client):
    response = client.post("/api/worlds/dimension", params={"dimension": "nether"})
    assert response.status_code == 200
    assert response.json()["dimension"] == "nether"


def test_switch_to_an_unknown_dimension(client):
    assert client.post("/api/worlds/dimension", params={"dimension": "moon"}).status_code == 400


def test_switch_dimension_without_a_world(client_without_world):
    assert client_without_world.post("/api/worlds/dimension", params={"dimension": "nether"}).status_code == 503


def test_block(client):
    data = client.get("/api/blocks/0/62/0").json()["data"]
    assert data["id"] == "water"
    assert data["properties"] == {"level": "0"}


@pytest.mark.parametrize("position", ["0/62/9999", "9999/62/0"])
def test_block_outside_the_loaded_chunks_is_not_found(client, position):
    response = client.get(f"/api/blocks/{position}")
    assert response.status_code == 404
    assert "NoneType" not in response.text


def test_block_without_a_world(client_without_world):
    assert client_without_world.get("/api/blocks/0/62/0").status_code == 503


def test_biome(client):
    assert client.get("/api/biomes/0/62/0").json()["data"]["id"] == "river"


def test_biome_outside_the_loaded_chunks_is_not_found(client):
    assert client.get("/api/biomes/0/62/9999").status_code == 404


def test_biome_without_a_world(client_without_world):
    assert client_without_world.get("/api/biomes/0/62/0").status_code == 503
