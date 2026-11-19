"""Copy a few chunks of an Anvil region file into a new, smaller region file.

The chunk payloads are copied as they are. Only the two header tables (chunk offsets
and timestamps) are rebuilt. `tests/world_files/r.0.0.mca` was made with:

    python tests/utilities/cut_region.py SOURCE.mca tests/world_files/r.0.0.mca 0,0 1,0 0,1 1,1

where each `x,z` is the chunk position inside the region (0 to 31).
"""

import sys

SECTOR = 4096


def cut_region(source: bytes, chunks: list[tuple[int, int]]) -> bytes:
    """A region file holding only `chunks`, taken from the region file bytes `source`."""
    offsets = bytearray(SECTOR)
    timestamps = bytearray(SECTOR)
    body = bytearray()
    next_sector = 2
    for x, z in chunks:
        slot = (x + z * 32) * 4
        start = int.from_bytes(source[slot:slot + 3], "big")
        count = source[slot + 3]
        if start == 0 or count == 0:
            raise ValueError(f"Chunk {x},{z} is not in the source region")
        body += source[start * SECTOR:(start + count) * SECTOR]
        offsets[slot:slot + 3] = next_sector.to_bytes(3, "big")
        offsets[slot + 3] = count
        timestamps[slot:slot + 4] = source[SECTOR + slot:SECTOR + slot + 4]
        next_sector += count
    return bytes(offsets) + bytes(timestamps) + bytes(body)


if __name__ == "__main__":
    source_path, target_path, *positions = sys.argv[1:]
    wanted = [(int(item.split(",")[0]), int(item.split(",")[1])) for item in positions]
    with open(source_path, "rb") as source_file:
        data = cut_region(source_file.read(), wanted)
    with open(target_path, "wb") as target_file:
        target_file.write(data)
