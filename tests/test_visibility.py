"""Which blocks the API sends: the ones the camera can see in at least one of the four views."""

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pytest
from orbispanora_lib.anvil import Block, EmptyChunk, EmptyRegion, World

from orbispanora_api.services import visibility
from orbispanora_api.services.visibility import AIR, SEE_THROUGH, SOLID, WATER, block_kind, visible
from orbispanora_api.services.world_service import _isometric_chunk_data  # pylint: disable=protected-access

#: Height of the test arrays; the middle chunk is at [:, 16:32, 16:32].
ROWS = 12
#: A position in the middle of the middle chunk, as (y, z, x) in the array.
MID = (4, 24, 24)


def area(cells: Dict[Tuple[int, int, int], int]) -> np.ndarray:
    """An array of kinds, air except ``cells``, given as offsets (dy, dz, dx) from ``MID``."""
    kinds = np.zeros((ROWS, 48, 48), dtype=np.uint8)
    for (dy, dz, dx), kind in cells.items():
        kinds[MID[0] + dy, MID[1] + dz, MID[2] + dx] = kind
    return kinds


def shown(kinds: np.ndarray, offset=(0, 0, 0)) -> bool:
    """Whether the block at ``offset`` from ``MID`` is visible."""
    dy, dz, dx = offset
    return bool(visible(kinds)[MID[0] + dy, MID[1] + dz - 16, MID[2] + dx - 16])


SIDES = [(0, 0, 1), (0, 0, -1), (0, 1, 0), (0, -1, 0)]
DIAGONALS = [(1, sz, sx) for sx in (1, -1) for sz in (1, -1)]


class TestRule:

    def test_a_block_alone_is_visible(self):
        assert shown(area({(0, 0, 0): SOLID}))

    def test_a_buried_block_is_not_visible(self):
        cells = {(0, 0, 0): SOLID, (1, 0, 0): SOLID, **{side: SOLID for side in SIDES}}
        assert not shown(area(cells))

    def test_air_is_never_sent(self):
        assert not visible(area({})).any()

    def test_a_block_with_a_block_on_each_ray_toward_the_camera_is_not_visible(self):
        # Its top is open, but in each view the block at p + d is drawn at the same place and covers it.
        cells = {(0, 0, 0): SOLID, **{diagonal: SOLID for diagonal in DIAGONALS}}
        assert not shown(area(cells))

    def test_a_block_further_along_the_ray_also_hides(self):
        cells = {(0, 0, 0): SOLID, **{(3, 3 * sz, 3 * sx): SOLID for _, sz, sx in DIAGONALS}}
        assert not shown(area(cells))

    @pytest.mark.parametrize("open_side", SIDES)
    def test_a_block_open_on_one_side_is_visible_from_that_side(self, open_side):
        cells = {(0, 0, 0): SOLID, (1, 0, 0): SOLID, **{side: SOLID for side in SIDES if side != open_side}}
        assert shown(area(cells))

    def test_a_wall_under_an_overhang_is_visible(self):
        # A wall three blocks high under a roof that sticks out one block on every side. The roof cell at
        # p + d covers the top wall block, but the blocks below it face air and the ray from them passes the roof.
        cells = {(0, 0, 0): SOLID, (-1, 0, 0): SOLID, (-2, 0, 0): SOLID}
        cells.update({(1, dz, dx): SOLID for dz in (-1, 0, 1) for dx in (-1, 0, 1)})
        kinds = area(cells)
        assert not shown(kinds)
        assert shown(kinds, (-1, 0, 0)) and shown(kinds, (-2, 0, 0))

    def test_see_through_blocks_are_drawn_and_hide_nothing(self):
        # Ice over water, leaves over the ground: both are sent.
        cells = {(0, 0, 0): WATER, (1, 0, 0): SEE_THROUGH, **{side: WATER for side in SIDES}}
        kinds = area(cells)
        assert shown(kinds) and shown(kinds, (1, 0, 0))

    def test_water_hides_the_floor_below_it(self):
        cells = {(0, 0, 0): SOLID, (1, 0, 0): WATER}
        cells.update({(dy, dz, dx): WATER for dy in (1, 2) for dz in (-2, -1, 0, 1, 2) for dx in (-2, -1, 0, 1, 2)})
        cells.update({(0, dz, dx): SOLID for dz in (-2, -1, 0, 1, 2) for dx in (-2, -1, 0, 1, 2)})
        kinds = area(cells)
        assert not shown(kinds)
        assert not shown(kinds, (1, 0, 0)), "water under water is not sent"
        assert shown(kinds, (2, 0, 0)), "the water surface is sent"

    def test_water_next_to_a_block_at_the_same_height_does_not_hide_it(self):
        # A pillar of two blocks; the lower one has water on every side and the upper one on top of it.
        cells = {(0, 0, 0): SOLID, (1, 0, 0): SOLID, **{side: WATER for side in SIDES}}
        assert shown(area(cells))
        cells.update({side: SOLID for side in SIDES})
        assert not shown(area(cells))

    def test_blocks_above_every_hiding_block_are_kept(self):
        kinds = area({(0, 0, 0): SOLID, (5, 0, 0): SEE_THROUGH})
        assert shown(kinds, (5, 0, 0))

    def test_a_ray_that_leaves_the_area_counts_as_clear(self):
        kinds = np.zeros((ROWS, 48, 48), dtype=np.uint8)
        kinds[0, 31, 31] = SOLID
        kinds[1:, :, :] = AIR
        assert visible(kinds)[0, 15, 15]


def test_a_block_that_several_blocks_hide_together_is_kept():
    """
    The top is open, but the blocks at the four sides one level up cover both halves of the top face in every
    view, and the four side neighbours cover the sides. The test keeps it: a known limit, costing one tile.
    """
    cells = {(0, 0, 0): SOLID, **{side: SOLID for side in SIDES}, **{(1, dz, dx): SOLID for _, dz, dx in SIDES}}
    assert shown(area(cells))


@pytest.mark.parametrize("name, kind", [
    ("minecraft:air", AIR), ("minecraft:cave_air", AIR), ("minecraft:water", WATER),
    ("minecraft:stone", SOLID), ("minecraft:grass_block", SOLID), ("create:shaft", SOLID),
    ("minecraft:oak_leaves", SEE_THROUGH), ("minecraft:glass", SEE_THROUGH), ("minecraft:white_stained_glass_pane", SEE_THROUGH),
    ("minecraft:ice", SEE_THROUGH), ("minecraft:spruce_slab", SEE_THROUGH), ("minecraft:oak_stairs", SEE_THROUGH),
    ("minecraft:wheat", SEE_THROUGH), ("minecraft:spruce_fence", SEE_THROUGH), ("minecraft:cobblestone_wall", SEE_THROUGH),
    ("minecraft:jack_o_lantern", SOLID), ("minecraft:piston_head", SOLID),
])
def test_block_kinds(name, kind):
    assert block_kind(name) == kind


def test_kinds_cache_keeps_the_most_recently_used():
    cache = visibility.KindsCache(2)
    loads = []

    def load(key):
        def run():
            loads.append(key)
            return visibility.ChunkKinds(np.zeros((1, 16, 16), np.uint8), key)
        return run

    for key in [1, 2, 1, 3, 1, 2]:
        cache.get((key, 0), load(key))
    # 2 was dropped when 3 came in (1 had just been used), so it is loaded twice.
    assert loads == [1, 2, 3, 2]
    off = visibility.KindsCache(0)
    off.get((1, 0), load(1))
    off.get((1, 0), load(1))
    assert loads[-2:] == [1, 1]


# --- Whole chunks, read from a world through the API's extraction ---


def build(tmp_path: Path, blocks, empty_chunks=()) -> World:
    """
    A world whose region 0,0 holds ``blocks``, a list of (x, y, z, name) in world coordinates, and the chunks
    ``empty_chunks`` stored without any section.
    """
    region = EmptyRegion(0, 0)
    for x, y, z, name in blocks:
        region.set_block(Block("minecraft", name), x, y, z)
    for chunk_x, chunk_z in empty_chunks:
        region.add_chunk(EmptyChunk(chunk_x, chunk_z))
    (tmp_path / "region").mkdir()
    region.save(str(tmp_path / "region" / "r.0.0.mca"))
    return World(str(tmp_path))


def sent(world: World, chunk_x: int, chunk_z: int):
    """The blocks sent for a chunk, as {(x, y, z) in world coordinates: name}."""
    data = _isometric_chunk_data(world, chunk_x, chunk_z)
    assert data is not None
    return {
        (chunk_x * 16 + x, y, chunk_z * 16 + z): data["palette"][block]
        for x, y, z, block in zip(data["x"], data["y"], data["z"], data["block"])
    }


def test_a_chunk_covered_with_ice_sends_the_ice_and_the_water_under_it(tmp_path):
    blocks = [(x, y, z, "stone") for x in range(48) for z in range(48) for y in (58, 59)]
    blocks += [(x, 60, z, "water") for x in range(48) for z in range(48)]
    blocks += [(x, 61, z, "ice") for x in range(48) for z in range(48)]
    world = build(tmp_path, blocks)
    got = sent(world, 1, 1)
    assert sorted(set(got.values())) == ["minecraft:ice", "minecraft:water"]
    assert len(got) == 2 * 256
    data = _isometric_chunk_data(world, 1, 1)
    assert data is not None and data["surface_y"] == 60, "water is the surface under the ice"


def test_the_ground_under_leaves_is_sent(tmp_path):
    blocks = [(x, 63, z, "grass_block") for x in range(48) for z in range(48)]
    blocks += [(x, 70, z, "oak_leaves") for x in range(48) for z in range(48)]
    got = sent(build(tmp_path, blocks), 1, 1)
    assert sum(name == "minecraft:grass_block" for name in got.values()) == 256


def test_the_cliff_face_at_the_edge_of_a_chunk_is_sent(tmp_path):
    # Chunk x = 0 is a plateau at y 70, chunk x = 1 is ground at y 60: the plateau's face at x = 15 is seen.
    blocks = [(x, y, z, "stone") for x in range(16) for z in range(48) for y in range(60, 71)]
    blocks += [(x, 60, z, "stone") for x in range(16, 48) for z in range(48)]
    got = sent(build(tmp_path, blocks), 0, 1)
    face = {(15, y, 20) for y in range(61, 70)}
    assert face <= set(got)
    assert (14, 65, 20) not in got, "the inside of the plateau is not sent"


def test_a_chunk_next_to_a_missing_chunk_keeps_its_edge(tmp_path):
    # Only chunk 0,0 exists: its blocks at x = 0 and z = 0 face chunks that do not exist.
    blocks = [(x, y, z, "stone") for x in range(16) for z in range(16) for y in range(60, 64)]
    got = sent(build(tmp_path, blocks), 0, 0)
    assert {(0, 60, 5), (5, 60, 0), (15, 60, 15)} <= set(got)
    assert (5, 61, 5) not in got


def test_a_chunk_without_sections_sends_nothing(tmp_path):
    world = build(tmp_path, [(40, 60, 40, "stone")], empty_chunks=[(0, 0)])
    data = _isometric_chunk_data(world, 0, 0)
    assert data is not None
    assert data["x"] == [] and data["surface_y"] == 320
