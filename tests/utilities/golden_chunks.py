"""Chunks whose isometric output is recorded in `tests/golden/isometric_chunks.json.gz`.

The recorded file is the reference of `tests/test_isometric_golden.py`: any change to the output of
`_isometric_chunk_data` (blocks, positions, order, shape of the result) makes that test fail. To record
a new reference on purpose, run `uv run python -m tests.utilities.make_golden` and commit the file.

Two worlds are used: the four chunks of the region file in `tests/world_files`, and a world built here
with the library's `EmptyRegion`. Each synthetic chunk exercises one rule of the extraction.
"""

import gzip
import json
from pathlib import Path
from typing import Callable, Dict, Optional

from orbispanora_lib.anvil import Block, EmptyChunk, EmptyRegion, World

from orbispanora_api.services.world_service import _isometric_chunk_data  # pylint: disable=protected-access
from tests.utilities.make_world import build_world

GOLDEN_FILE = Path(__file__).resolve().parents[1] / "golden" / "isometric_chunks.json.gz"

#: Chunks of the test region file.
FIXTURE_CHUNKS = [(0, 0), (0, 1), (1, 0), (1, 1)]

Put = Callable[[int, int, int, str], None]


def _flat(put: Put) -> None:
    """Stone and a layer of grass: every column has the same top."""
    for x in range(16):
        for z in range(16):
            put(x, 62, z, "stone")
            put(x, 63, z, "grass_block")


def _hill(put: Put) -> None:
    """Tops from y 60 to 67, rising along x + z."""
    for x in range(16):
        for z in range(16):
            top = 60 + (x + z) // 4
            put(x, top - 1, z, "dirt")
            put(x, top, z, "grass_block")


def _canopy(put: Put) -> None:
    """Stone at y 64 with leaves, glass, grass and water on top, which the extraction treats as invisible or not."""
    for x in range(16):
        for z in range(16):
            put(x, 64, z, "water" if x < 4 else "stone")
            if (x + z) % 3 == 0:
                put(x, 65, z, "oak_leaves")
            elif x % 4 == 1 and z % 4 == 1:
                put(x, 65, z, "glass")
            elif (x * 3 + z) % 7 == 0:
                put(x, 65, z, "short_grass")


def _overhang(put: Put) -> None:
    """A ledge over air: the columns with x < 8 have stone at 56 to 60 above an air gap, the others stop at 52."""
    for x in range(16):
        for z in range(16):
            for y in range(50, 53):
                put(x, y, z, "stone")
            if x < 8:
                for y in range(56, 61):
                    put(x, y, z, "stone")


def _hole(put: Put) -> None:
    """Ground at y 64 and below it, except one column that holds no block at all."""
    for x in range(16):
        for z in range(16):
            if (x, z) == (7, 7):
                continue
            put(x, 63, z, "stone")
            put(x, 64, z, "grass_block")


def _pillars(put: Put) -> None:
    """Ground at y 64 with four-by-four stone pillars up to y 130, across six sections."""
    for x in range(16):
        for z in range(16):
            put(x, 64, z, "grass_block")
            if x < 4 and z < 4:
                for y in range(48, 131):
                    put(x, y, z, "stone")


def _water(put: Put) -> None:
    """Water only."""
    for x in range(16):
        for z in range(16):
            put(x, 62, z, "water")


SYNTHETIC_BUILDERS: Dict[str, Callable[[Put], None]] = {
    "flat": _flat,
    "hill": _hill,
    "canopy": _canopy,
    "overhang": _overhang,
    "hole": _hole,
    "pillars": _pillars,
    "water": _water,
}
#: A chunk that is stored but has no section.
EMPTY_CHUNK_NAME = "no_sections"
SYNTHETIC_NAMES = [*SYNTHETIC_BUILDERS, EMPTY_CHUNK_NAME]


def build_synthetic_world(target: Path) -> Path:
    """Write a world with one chunk per synthetic case, side by side along x in region 0,0."""
    region = EmptyRegion(0, 0)
    for chunk_x, builder in enumerate(SYNTHETIC_BUILDERS.values()):

        def put(x: int, y: int, z: int, block: str, chunk_x: int = chunk_x) -> None:
            region.set_block(Block("minecraft", block), chunk_x * 16 + x, y, z)

        builder(put)
    region.add_chunk(EmptyChunk(len(SYNTHETIC_BUILDERS), 0))
    (target / "region").mkdir(parents=True)
    region.save(str(target / "region" / "r.0.0.mca"))
    return target


def collect(workdir: Path) -> Dict[str, Optional[dict]]:
    """The output of `_isometric_chunk_data` for every recorded chunk, as plain JSON data."""
    fixture = World(str(build_world(workdir / "fixture")))
    synthetic = World(str(build_synthetic_world(workdir / "synthetic")))
    found: Dict[str, Optional[dict]] = {}
    for x, z in FIXTURE_CHUNKS:
        found[f"fixture/{x},{z}"] = _isometric_chunk_data(fixture, x, z)
    found["fixture/9,9"] = _isometric_chunk_data(fixture, 9, 9)
    for chunk_x, name in enumerate(SYNTHETIC_NAMES):
        found[f"synthetic/{name}"] = _isometric_chunk_data(synthetic, chunk_x, 0)
    found["synthetic/outside"] = _isometric_chunk_data(synthetic, 30, 0)
    # JSON round trip: the comparison is on the data that goes over the wire.
    return json.loads(json.dumps(found))


def write_golden(data: Dict[str, Optional[dict]]) -> None:
    """Write the reference file. The gzip header holds no time, so the same data gives the same bytes."""
    GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(GOLDEN_FILE, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as packed:
        packed.write(json.dumps(data, separators=(",", ":")).encode("utf-8"))


def read_golden() -> Dict[str, Optional[dict]]:
    """The recorded reference."""
    with gzip.open(GOLDEN_FILE, "rb") as packed:
        return json.loads(packed.read())
