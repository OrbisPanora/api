"""
Which blocks of a chunk the camera can see, in any of the four views of the viewer.

The viewer draws every block as a sprite of a cube, with an orthographic projection: every ray from the camera
runs along the same direction. In the default view that direction is (1, 1, 1) from a block toward the camera,
and the four 90 degree views use (±1, 1, ±1). The blocks at p, p + d, p + 2d, ... are drawn at the same screen
position, so a block that hides others covers the whole sprite of a block behind it.

Each block has a kind:

- air: never drawn, hides nothing;
- see-through: drawn, hides nothing (leaves, glass, plants, slabs and other blocks whose sprite does not cover
  the whole cube);
- water: drawn, hides the blocks below it but not the blocks next to it at the same height (its sprite is
  half transparent);
- solid: drawn, hides what is behind it.

A block is visible in one view if both hold:

- one of the three faces turned to the camera (the top and two sides) touches a cell that does not hide it;
- no cell on the line p + d, p + 2d, ... hides it.

This never drops a visible block. It keeps a few blocks that several blocks hide together, each covering part
of the sprite. An exact test, which traces the rays through each of the six triangles of the sprite, was tried
on a large world: it sent about 2 % fewer blocks, took about four times longer, and looked the same in the
viewer.

The test looks at the chunk and its eight neighbours. A ray that leaves this area counts as clear, so a block
near the area's edge is kept rather than dropped.
"""

from typing import Callable, Dict, Sequence, Tuple

import numpy as np

#: Kinds of block, stored as one byte per block.
AIR, SEE_THROUGH, WATER, SOLID = 0, 1, 2, 3

AIR_BLOCKS = frozenset({"minecraft:air", "minecraft:cave_air", "minecraft:void_air"})
WATER_BLOCKS = frozenset({"minecraft:water"})
#: Blocks drawn but not hiding anything behind them, by name without the namespace.
SEE_THROUGH_NAMES = frozenset({
    "ice", "tall_grass", "grass", "short_grass", "fern", "large_fern", "vine", "torch", "lily_pad",
    "redstone_wire", "lever", "wheat", "carrots", "potatoes", "beetroots", "dandelion", "poppy", "blue_orchid",
    "allium", "azure_bluet", "oxeye_daisy", "cornflower", "lily_of_the_valley", "wither_rose", "sunflower",
    "lilac", "rose_bush", "peony", "dead_bush", "seagrass", "tall_seagrass", "kelp", "kelp_plant", "sugar_cane",
    "glow_lichen", "snow", "ladder", "chain", "lantern", "soul_lantern", "flower_pot", "cobweb", "scaffolding",
    "bell", "comparator", "repeater", "cactus", "bamboo", "sweet_berry_bush", "hanging_roots", "spore_blossom",
    "brown_mushroom", "red_mushroom", "crimson_fungus", "warped_fungus", "crimson_roots", "warped_roots",
    "nether_sprouts", "twisting_vines", "twisting_vines_plant", "weeping_vines", "weeping_vines_plant",
    "cave_vines", "cave_vines_plant", "small_dripleaf", "big_dripleaf", "big_dripleaf_stem", "pointed_dripstone",
    "end_rod", "lightning_rod", "tripwire", "tripwire_hook", "iron_bars", "cake", "candle", "pitcher_plant",
    "torchflower", "pink_petals", "moss_carpet", "conduit", "turtle_egg", "sea_pickle", "nether_wart",
    "melon_stem", "pumpkin_stem", "attached_melon_stem", "attached_pumpkin_stem", "cocoa", "farmland",
    "dirt_path", "enchanting_table", "brewing_stand", "anvil", "chipped_anvil", "damaged_anvil", "hopper",
    "grindstone", "stonecutter", "lectern", "campfire", "soul_campfire", "spawner", "chest", "trapped_chest",
    "ender_chest", "slime_block", "honey_block", "amethyst_cluster", "azalea", "flowering_azalea",
    "end_portal_frame", "frosted_ice", "sculk_shrieker", "trial_spawner", "vault", "player_head", "zombie_head",
    "creeper_head", "dragon_head", "piglin_head",
})
#: Name endings of blocks that do not hide what is behind them.
SEE_THROUGH_SUFFIXES = (
    "_leaves", "glass", "_glass_pane", "_pane", "_sapling", "_fence", "_fence_gate", "_wall", "_trapdoor", "_door",
    "_carpet", "_button", "_pressure_plate", "_sign", "_hanging_sign", "_torch", "rail", "_slab", "_stairs",
    "_tulip", "_banner", "_bed", "_candle", "_wall_head", "_skull", "_coral", "_coral_fan", "_coral_wall_fan",
    "_shulker_box", "_mushroom", "_propagule", "_amethyst_bud", "cauldron", "_grate",
)

#: Camera side of the four views, as (sx, sz): the view direction is (sx, 1, sz).
_VIEWS = ((1, 1), (-1, 1), (1, -1), (-1, -1))
#: Cells of the chunk and of the neighbours on each side.
_SIZE = 16
_AREA = 3 * _SIZE


def block_kind(name: str) -> int:
    """The kind of a block from its name with the namespace, for example ``minecraft:stone``."""
    if name in AIR_BLOCKS:
        return AIR
    if name in WATER_BLOCKS:
        return WATER
    short = name.split(":", 1)[-1]
    if short in SEE_THROUGH_NAMES or short.endswith(SEE_THROUGH_SUFFIXES):
        return SEE_THROUGH
    return SOLID


def block_kinds(names: Sequence[str]) -> np.ndarray:
    """The kind of each name, as a ``uint8`` array to index with palette indices."""
    return np.fromiter((block_kind(name) for name in names), dtype=np.uint8, count=len(names))


def _shifted(values: np.ndarray, dy: int, dz: int, dx: int, fill: bool) -> np.ndarray:
    """``out[p] = values[p + (dy, dz, dx)]``, and ``fill`` where that cell is outside the array."""
    out = np.full_like(values, fill)
    rows, depth, width = values.shape
    if abs(dy) >= rows or abs(dz) >= depth or abs(dx) >= width:
        return out
    out[max(-dy, 0):rows + min(-dy, 0), max(-dz, 0):depth + min(-dz, 0), max(-dx, 0):width + min(-dx, 0)] = \
        values[max(dy, 0):rows + min(dy, 0), max(dz, 0):depth + min(dz, 0), max(dx, 0):width + min(dx, 0)]
    return out


def _along_ray(values: np.ndarray, sx: int, sz: int) -> np.ndarray:
    """``out[p]`` is True if ``values`` is True at p, p + d, p + 2d, ... with d = (1, sz, sx) in (y, z, x)."""
    out = values.copy()
    step = 1
    # Past the smallest side of the array the ray has left it, and outside counts as True.
    while step < min(values.shape):
        out &= _shifted(out, step, step * sz, step * sx, True)
        step *= 2
    return out


def visible(kinds: np.ndarray) -> np.ndarray:
    """
    Which blocks of the middle chunk are visible in at least one of the four views.

    Parameters
    ----------
    kinds
        The kinds of the chunk and its eight neighbours, ``uint8`` of shape ``(height, 48, 48)``, indexed
        ``[y][z][x]``, with the chunk at ``[:, 16:32, 16:32]``. A neighbour that does not exist is air.

    Returns
    -------
    numpy.ndarray
        Boolean array of shape ``(height, 16, 16)``: True for each block to draw.
    """
    rows = kinds.shape[0]
    hides_nothing = kinds <= SEE_THROUGH
    # Above the highest block that hides something every ray is clear, so those rows are left out.
    hiding_rows = np.flatnonzero(~hides_nothing.all(axis=(1, 2)))
    top = min(rows, int(hiding_rows[-1]) + 2) if hiding_rows.size else 0
    result = np.zeros((rows, _SIZE, _SIZE), dtype=bool)
    drawn = kinds[:top] != AIR
    if not drawn[:, _SIZE:2 * _SIZE, _SIZE:2 * _SIZE].any():
        return result | (kinds[:, _SIZE:2 * _SIZE, _SIZE:2 * _SIZE] != AIR)

    every_clear = hides_nothing[:top]
    every_water = kinds[:top] == WATER
    keep = np.zeros((top, _SIZE, _SIZE), dtype=bool)
    for sx, sz in _VIEWS:
        # A view only looks toward +sx and +sz, so it needs the chunk and the neighbours on that side.
        xs = slice(_SIZE, _AREA) if sx > 0 else slice(0, 2 * _SIZE)
        zs = slice(_SIZE, _AREA) if sz > 0 else slice(0, 2 * _SIZE)
        clear, water = every_clear[:, zs, xs], every_water[:, zs, xs]

        def open_at(offset: Tuple[int, int, int], clear=clear, water=water, sx: int = sx, sz: int = sz) -> np.ndarray:
            """Cells at ``offset`` that do not hide the block; water at the same height does not hide."""
            dy, dz, dx = offset
            cells = _shifted(clear, dy, dz * sz, dx * sx, True)
            if dy == 0:
                cells |= _shifted(water, 0, dz * sz, dx * sx, False) & ~water
            return cells

        line = _along_ray(_shifted(clear, 1, sz, sx, True), sx, sz)
        seen = line & (open_at((1, 0, 0)) | open_at((0, 0, 1)) | open_at((0, 1, 0)))
        # The chunk is the first half of the cropped area on the camera side, the second half otherwise.
        z0, x0 = (0 if sz > 0 else _SIZE), (0 if sx > 0 else _SIZE)
        keep |= seen[:, z0:z0 + _SIZE, x0:x0 + _SIZE]
    result[:top] = keep & drawn[:, _SIZE:2 * _SIZE, _SIZE:2 * _SIZE]
    # Blocks above every hiding block are drawn: nothing can hide them.
    result[top:] = kinds[top:, _SIZE:2 * _SIZE, _SIZE:2 * _SIZE] != AIR
    return result


def area_kinds(chunk_x: int, chunk_z: int, kinds_of: Callable[[int, int], "ChunkKinds | None"]) -> np.ndarray:
    """
    The kinds of a chunk and its eight neighbours as one array, with the rows of the chunk.

    ``kinds_of(x, z)`` gives the kinds of a chunk, or None if it does not exist. The rows follow the middle
    chunk; a neighbour with other heights is placed by its own ``min_y``.
    """
    middle = kinds_of(chunk_x, chunk_z)
    assert middle is not None
    rows = middle.kinds.shape[0]
    area = np.zeros((rows, _AREA, _AREA), dtype=np.uint8)
    for dz in (-1, 0, 1):
        for dx in (-1, 0, 1):
            found = middle if dx == dz == 0 else kinds_of(chunk_x + dx, chunk_z + dz)
            if found is None:
                continue
            first = max(found.min_y, middle.min_y)
            last = min(found.min_y + found.kinds.shape[0], middle.min_y + rows)
            if first >= last:
                continue
            z0, x0 = (dz + 1) * _SIZE, (dx + 1) * _SIZE
            area[first - middle.min_y:last - middle.min_y, z0:z0 + _SIZE, x0:x0 + _SIZE] = \
                found.kinds[first - found.min_y:last - found.min_y]
    return area


class ChunkKinds:
    """The kind of each block of one chunk: ``kinds`` is ``uint8`` of shape ``(height, 16, 16)``."""

    __slots__ = ("kinds", "min_y")

    def __init__(self, kinds: np.ndarray, min_y: int):
        self.kinds = kinds
        self.min_y = min_y


class KindsCache:
    """The kinds of the most recently used chunks of one world, at most ``size`` of them (about 98 KB each)."""

    def __init__(self, size: int):
        self.size = size
        self._items: Dict[Tuple[int, int], "ChunkKinds | None"] = {}

    def get(self, key: Tuple[int, int], load: Callable[[], "ChunkKinds | None"]) -> "ChunkKinds | None":
        """The cached kinds of a chunk, or ``load()`` stored for next time."""
        value = self._items[key] if key in self._items else load()
        self.put(key, value)
        return value

    def put(self, key: Tuple[int, int], value: "ChunkKinds | None") -> None:
        """Store the kinds of a chunk as the most recently used, and drop the oldest beyond ``size``."""
        self._items.pop(key, None)
        if self.size > 0:
            self._items[key] = value
            while len(self._items) > self.size:
                del self._items[next(iter(self._items))]
