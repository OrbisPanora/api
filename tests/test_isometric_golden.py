"""The output of `_isometric_chunk_data` must stay equal to the recorded reference.

The reference is `tests/golden/isometric_chunks.json.gz`, recorded from the code before it was rewritten
(see `tests/utilities/golden_chunks.py`). The chunk results hold positions and a palette; the reference holds
the screen positions that the viewer computes from them. A failure names the first block that differs. If the change is
meant, record the reference again with `uv run python -m tests.utilities.make_golden` and say why in the
commit.
"""

import pytest

from tests.utilities.golden_chunks import SYNTHETIC_NAMES, collect, read_golden

RECORDED = read_golden()


def recorded(key: str) -> dict:
    """The recorded output of a chunk that exists."""
    value = RECORDED[key]
    assert value is not None, key
    return value


@pytest.fixture(scope="module")
def current(tmp_path_factory):
    """The output of the code under test, for every recorded chunk."""
    return collect(tmp_path_factory.mktemp("golden"))


def first_difference(expected, actual) -> str:
    """A short description of where two chunk outputs differ."""
    if expected is None or actual is None:
        return f"expected {'no chunk' if expected is None else 'a chunk'}, got {'no chunk' if actual is None else 'a chunk'}"
    for field in sorted(set(expected) | set(actual)):
        if field == "surface_blocks":
            continue
        if expected.get(field) != actual.get(field):
            return f"field {field!r}: expected {expected.get(field)!r}, got {actual.get(field)!r}"
    wanted, got = expected["surface_blocks"], actual["surface_blocks"]
    for index, (left, right) in enumerate(zip(wanted, got)):
        if left != right:
            return f"block {index}: expected {left}, got {right}"
    return f"expected {len(wanted)} blocks, got {len(got)}"


def test_the_same_chunks_are_recorded(current):
    assert sorted(current) == sorted(RECORDED)


@pytest.mark.parametrize("key", sorted(RECORDED))
def test_output_equals_the_reference(current, key):
    assert current[key] == RECORDED[key], first_difference(RECORDED[key], current[key])


def test_the_reference_covers_the_rules_it_is_meant_to_pin_down():
    """Guards against a reference that was recorded from the wrong chunks."""
    flat = recorded("synthetic/flat")
    assert flat["palette"] == 63 and flat["heightmap"] == 256
    # A chunk that is stored but has no section has the same shape as any other chunk, without blocks.
    empty = recorded("synthetic/no_sections")
    assert empty["surface_blocks"] == [] and empty["heightmap"] == 0 and empty["palette"] == 320
    assert RECORDED["fixture/9,9"] is None and RECORDED["synthetic/outside"] is None
    names = {block[0] for key, value in RECORDED.items() if value and "surface_blocks" in value for block in value["surface_blocks"]}
    assert {"water.webp", "oak_leaves.webp", "glass.webp", "short_grass.webp", "stone.webp"} <= names
    # Blocks come in the order z, then x, then y (the draw order).
    hill = recorded("synthetic/hill")["surface_blocks"]
    assert hill[0][1:] != hill[1][1:]
    assert all(f"synthetic/{name}" in RECORDED for name in SYNTHETIC_NAMES)
    assert len(SYNTHETIC_NAMES) == 12
