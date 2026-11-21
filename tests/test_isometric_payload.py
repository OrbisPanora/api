"""The isometric chunk response: positions and a palette, with no screen positions."""

from typing import Optional

import pytest

FIELDS = {"chunk_x", "chunk_z", "surface_y", "palette", "x", "y", "z", "block"}


def to_screen(data: Optional[dict]) -> Optional[dict]:
    """
    A chunk result (positions and a palette) as the list of blocks with screen positions that the API sent
    before 0.2.0: ``[sprite, x, y]`` with ``x = 16 * (gx - gz)`` and ``y = 8 * (gx + gz) - 16 * y``. This is the
    projection that the viewer does.
    """
    if data is None:
        return None
    sprites = [name.split(":")[1] + ".webp" for name in data["palette"]]
    blocks = []
    for x, y, z, block in zip(data["x"], data["y"], data["z"], data["block"]):
        global_x = data["chunk_x"] * 16 + x
        global_z = data["chunk_z"] * 16 + z
        blocks.append([sprites[block], float(16 * (global_x - global_z)), float(8 * (global_x + global_z) - 16 * y)])
    return {"chunk_x": data["chunk_x"], "chunk_z": data["chunk_z"], "surface_blocks": blocks}


def isometric(client, x, z):
    response = client.get(f"/api/chunks/{x}/{z}/0", params={"mode": "isometric"})
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.parametrize("chunk", [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_the_response_has_the_documented_fields(client, chunk):
    data = isometric(client, *chunk)
    assert set(data) == FIELDS
    assert (data["chunk_x"], data["chunk_z"]) == chunk
    count = len(data["x"])
    assert count > 0 and len(data["y"]) == len(data["z"]) == len(data["block"]) == count


def test_positions_and_palette_indices_are_valid(client):
    data = isometric(client, 1, 1)
    assert all(0 <= value < 16 for value in data["x"]) and all(0 <= value < 16 for value in data["z"])
    assert all(isinstance(value, int) for value in data["y"])
    assert set(data["block"]) == set(range(len(data["palette"]))), "every palette entry is used and none is missing"
    assert len(set(data["palette"])) == len(data["palette"])
    assert all(":" in name for name in data["palette"]), "names keep their namespace"


def test_blocks_are_in_the_order_z_then_x_then_y(client):
    data = isometric(client, 1, 1)
    keys = list(zip(data["z"], data["x"], data["y"]))
    assert keys == sorted(keys)


def test_surface_y_is_a_height_of_the_chunk(client):
    data = isometric(client, 1, 1)
    assert -64 <= data["surface_y"] < 320


def test_no_screen_positions_are_sent(client):
    data = isometric(client, 0, 0)
    assert "surface_blocks" not in data and "heightmap" not in data


def test_the_viewers_projection_gives_the_screen_positions_of_a_known_block(client):
    data = isometric(client, 1, 0)
    screen = to_screen(data)
    assert screen is not None
    sprite, x_screen, y_screen = screen["surface_blocks"][0]
    gx, gz, y = 16 + data["x"][0], data["z"][0], data["y"][0]
    assert (x_screen, y_screen) == (16 * (gx - gz), 8 * (gx + gz) - 16 * y)
    assert sprite == data["palette"][data["block"][0]].split(":")[1] + ".webp"


def test_a_chunk_that_does_not_exist_is_not_found(client):
    assert client.get("/api/chunks/9/9/0", params={"mode": "isometric"}).status_code == 404


def test_the_payload_is_described_in_the_openapi_schema(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert set(schemas["IsometricChunkResponse"]["properties"]) == FIELDS


def test_the_payload_is_smaller_than_the_old_one(client):
    """About 35 bytes per block as [sprite, x, y] against about 12 as four small numbers."""
    response = client.get("/api/chunks/1/1/0", params={"mode": "isometric"})
    count = len(response.json()["data"]["x"])
    assert len(response.content) < count * 20 + 400
