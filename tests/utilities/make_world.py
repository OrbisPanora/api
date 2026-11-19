"""A small Minecraft world for the tests, built from the region file in `tests/world_files`.

The region file holds four chunks (0,0 to 1,1) cut from a larger region, see
`cut_region.py`. A world folder also needs a `level.dat`, which is written here.
"""

import shutil
import zipfile
from pathlib import Path

from nbt import nbt

REGION_FIXTURE = Path(__file__).resolve().parents[1] / "world_files" / "r.0.0.mca"


def build_world(target: Path) -> Path:
    """Create a world folder at `target` and return it."""
    (target / "region").mkdir(parents=True)
    shutil.copy(REGION_FIXTURE, target / "region" / "r.0.0.mca")
    level = nbt.NBTFile()
    data = nbt.TAG_Compound(name="Data")
    data.tags.append(nbt.TAG_String(name="LevelName", value="test world"))
    data.tags.append(nbt.TAG_Int(name="DataVersion", value=3955))
    level.tags.append(data)
    level.write_file(str(target / "level.dat"))
    return target


def build_world_zip(zip_path: Path, folder_name: str = "world") -> Path:
    """Create a zip file holding a world folder named `folder_name` and return its path."""
    staging = zip_path.parent / f"{zip_path.stem}-staging"
    world = build_world(staging / folder_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(world.rglob("*")):
            archive.write(path, path.relative_to(staging))
    shutil.rmtree(staging)
    return zip_path
