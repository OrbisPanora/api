"""Record the reference output of `_isometric_chunk_data` (see `golden_chunks.py`).

Run it only when the output is meant to change:

    uv run python -m tests.utilities.make_golden
"""

import tempfile
from pathlib import Path

from tests.utilities.golden_chunks import GOLDEN_FILE, collect, write_golden


def main() -> None:
    """Build the chunks, record their output and print a summary."""
    with tempfile.TemporaryDirectory() as workdir:
        data = collect(Path(workdir))
    write_golden(data)
    for key, value in data.items():
        count = "no chunk" if value is None else len(value.get("surface_blocks", value.get("blocks", [])))
        print(f"{key:28} {count}")
    print(f"Wrote {GOLDEN_FILE} ({GOLDEN_FILE.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
