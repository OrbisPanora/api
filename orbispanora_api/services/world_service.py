"""
World service for managing Minecraft world instance.
Singleton pattern to ensure only one World instance is loaded.
"""

import asyncio
import concurrent.futures
import os
import shutil
import tempfile
import time
import traceback
import weakref
import zipfile
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import numpy as np
from orbispanora_lib.anvil import Chunk, OldBlock, World

from ..models.responses import (
    AreaHeightmapResponse,
    BiomeDataResponse,
    BlockDataResponse,
    ChunkDataResponse,
    IsometricChunkResponse,
    TileDataResponse,
    WorldInfoResponse,
)
from ..settings import get_settings
from ..utils.errors import WorldNotLoadedError
from ..utils.timing import Stopwatch
from . import visibility
from .zip_safety import safe_extract

#: The world a worker process has open: ``((path, dimension), World)``. A worker keeps one world at a time, so
#: the memory of an earlier world is released when another one is asked for.
_worker_state: Optional[Tuple[Tuple[str, str], World]] = None


def worker_world(world_path: str, dimension: str) -> Tuple[World, bool]:
    """
    The ``World`` of this worker process for a path and a dimension, and whether it was opened just now.

    Reading is lazy: a region file is read when a chunk of it is asked for, and the number of regions and
    chunks kept is limited by the settings ``world_region_cache`` and ``world_chunk_cache``.
    """
    global _worker_state  # pylint: disable=global-statement
    key = (world_path, dimension)
    if _worker_state is not None and _worker_state[0] == key:
        return _worker_state[1], False
    if _worker_state is not None:
        _worker_state[1].close()
        _worker_state = None
    world = _open_world(world_path, dimension)
    _worker_state = (key, world)
    return world, True


def _open_world(world_path: str, dimension: str) -> World:
    """A ``World`` whose caches have the sizes of the settings."""
    settings = get_settings()
    return World(
        world_path,
        dimension=dimension,
        chunk_cache_size=settings.world_chunk_cache,
        region_cache_size=settings.world_region_cache,
    )

#: Value of ``surface_y`` for a chunk with no block.
_NO_SURFACE = 320
#: Kinds of block of the chunks used recently, per world (see ``visibility.KindsCache``).
_kinds_caches: "weakref.WeakKeyDictionary[World, visibility.KindsCache]" = weakref.WeakKeyDictionary()


def _kinds_cache(world: World) -> visibility.KindsCache:
    """The cache of block kinds of a world, created on first use with the size of the settings."""
    cache = _kinds_caches.get(world)
    if cache is None:
        cache = _kinds_caches[world] = visibility.KindsCache(get_settings().world_kinds_cache)
    return cache


def _chunk_kinds(world: World, chunk_x: int, chunk_z: int) -> Optional[visibility.ChunkKinds]:
    """The kind of each block of a chunk, or None if the chunk does not exist."""
    chunk = world.get_chunk(chunk_x, chunk_z)
    if not isinstance(chunk, Chunk):
        return None
    blocks = chunk.block_array()
    return visibility.ChunkKinds(visibility.block_kinds(blocks.names)[blocks.indices], blocks.min_y)


def _surface_y(kinds: np.ndarray, min_y: int, ys: np.ndarray) -> int:
    """
    The lowest surface of a chunk: for each column the height of the highest block that hides what is below it
    (water or solid), and the lowest of these. Without such a block, the lowest block sent, or 320 if none.
    """
    hiding = kinds >= visibility.WATER
    has_top = hiding.any(axis=0)
    if has_top.any():
        top_row = kinds.shape[0] - 1 - hiding[::-1].argmax(axis=0)
        return int(top_row[has_top].min()) + min_y
    return int(ys.min()) + min_y if ys.size else _NO_SURFACE


def _isometric_chunk_data(world: World, chunk_x: int, chunk_z: int, watch: Optional[Stopwatch] = None) -> Optional[dict]:
    """
    The blocks of a chunk that are sent to the viewer, or None if the chunk does not exist.

    The result is a dict with the fields of ``IsometricChunkResponse``: ``surface_y`` (see ``_surface_y``),
    ``palette`` (the block names that occur), and for each block its position inside the chunk (``x``, ``y``,
    ``z``) and its index in the palette (``block``). The blocks are those the camera can see in at least one of
    the four views (see ``visibility``), in the order z, x, y. The viewer projects the positions itself.

    When ``watch`` is given, it gets one lap per phase: ``chunk`` (region read, decompression and
    NBT parsing), ``decode`` (the chunk's blocks as an array), ``neighbours`` (the kinds of the eight chunks
    around it), ``visibility`` (block selection) and ``project`` (the lists sent to the client).
    """
    watch = watch or Stopwatch()
    chunk = world.get_chunk(chunk_x, chunk_z)
    watch.lap("chunk")
    if not isinstance(chunk, Chunk):
        return None

    blocks = chunk.block_array()
    indices, names, min_y = blocks.indices, blocks.names, blocks.min_y
    middle = visibility.ChunkKinds(visibility.block_kinds(names)[indices], min_y)
    watch.lap("decode")

    cache = _kinds_cache(world)
    cache.put((chunk_x, chunk_z), middle)

    def kinds_of(x: int, z: int) -> Optional[visibility.ChunkKinds]:
        return middle if (x, z) == (chunk_x, chunk_z) else cache.get((x, z), lambda: _chunk_kinds(world, x, z))

    area = visibility.area_kinds(chunk_x, chunk_z, kinds_of)
    watch.lap("neighbours")

    shown = visibility.visible(area)
    # Blocks in the order z, x, y (y going up), which is the draw order of the default view.
    zs, xs, ys = np.nonzero(shown.transpose(1, 2, 0))
    ids = indices[ys, zs, xs]
    watch.lap("visibility")

    # Keep only the block names that occur, numbered in the order of the chunk's own palette.
    used, inverse = np.unique(ids, return_inverse=True)
    result = _isometric_result(chunk_x, chunk_z, _surface_y(middle.kinds, min_y, ys))
    result.update(
        palette=[names[i] for i in used.tolist()],
        x=xs.tolist(),
        y=(ys + min_y).tolist(),
        z=zs.tolist(),
        block=inverse.tolist(),
    )
    watch.lap("project")
    return result


def _isometric_result(chunk_x: int, chunk_z: int, surface_y: int) -> dict:
    """An isometric chunk result without blocks."""
    return {
        "chunk_x": chunk_x, "chunk_z": chunk_z, "surface_y": surface_y,
        "palette": [], "x": [], "y": [], "z": [], "block": [],
    }


def _worker_get_chunk_isometric_timed(
    world_path: str, dimension: str, chunk_x: int, chunk_z: int, submitted: Optional[float] = None
) -> Tuple[Optional[dict], Dict[str, float]]:
    """
    Isometric chunk data computed in a worker process, with the time each phase took (milliseconds).

    ``submitted`` is ``time.time()`` at the moment the request was handed to the pool; the
    ``queue`` phase is the wait until this function starts. ``finished`` is ``time.time()`` at the
    end, so the caller can compute how long the result took to come back (``return``). The note
    ``cold`` is 1.0 if this process had to open the world for this request.
    """
    started = time.time()
    watch = Stopwatch()
    cold = False
    try:
        world, cold = worker_world(world_path, dimension)
        watch.lap("world")
        data = _isometric_chunk_data(world, chunk_x, chunk_z, watch)
    except Exception as e:
        print(f"Worker error for isometric chunk ({chunk_x}, {chunk_z}): {e}")
        data = None
    timings = {"queue": max(0.0, (started - submitted) * 1000) if submitted else 0.0}
    timings.update(watch.phases)
    timings["cold"] = 1.0 if cold else 0.0
    timings["finished"] = time.time()
    return data, timings


def _worker_get_chunk_isometric(world_path: str, dimension: str, chunk_x: int, chunk_z: int) -> Optional[dict]:
    """
    Worker function to get chunk data in isometric mode in a separate process.
    This allows multiple chunk requests to run in parallel.
    """
    return _worker_get_chunk_isometric_timed(world_path, dimension, chunk_x, chunk_z)[0]


class WorldService:
    """Singleton service for managing Minecraft world."""

    _instance: Optional['WorldService'] = None
    _world: Optional[World] = None
    _world_path: Optional[str] = None
    _executor: Optional[concurrent.futures.ProcessPoolExecutor] = None



    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super(WorldService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize world service."""
        # Initialize executor for async tasks
        if self._executor is None:
            self._executor = self._new_pool()

    @staticmethod
    def _new_pool() -> concurrent.futures.ProcessPoolExecutor:
        """A pool with the number of workers of the settings."""
        return concurrent.futures.ProcessPoolExecutor(max_workers=get_settings().workers)

    @property
    def executor(self) -> concurrent.futures.ProcessPoolExecutor:
        """The pool of worker processes, shared by every route that computes chunks."""
        if self._executor is None:
            self._executor = self._new_pool()
        return self._executor

    def _restart_workers(self) -> None:
        """
        Replace the worker processes. Called when another world is loaded, so the memory the workers hold for
        the previous world is released. Requests that are running finish first; the old workers then exit.
        """
        previous = self._executor
        self._executor = self._new_pool()
        if previous is not None:
            previous.shutdown(wait=False)

    def shutdown(self):
        """Stop the worker processes. Called when the application shuts down."""
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None

    def _load_world(self):
        """Load the Minecraft world."""
        try:
            configured = get_settings().world_path
            if configured is None:
                raise ValueError("No world configured. Set ORBISPANORA_WORLD_PATH or upload a world.")
            world_path = str(configured)
            print(f"Loading world from: {world_path}")
            self._world = _open_world(world_path, get_settings().world_dimension)
            self._world_path = world_path
            print("World loaded successfully")
        except Exception as e:
            print(f"Failed to load world: {e}")
            raise

    @property
    def world(self) -> World:
        """Get the world instance with lazy loading."""
        if self._world is None:
            self._load_world()
        if self._world is None:
            raise WorldNotLoadedError()
        return self._world

    @property
    def world_path(self) -> Optional[str]:
        """Get the path to the currently loaded world."""
        return self._world_path

    def load_world_from_path(self, world_path: str, dimension: Optional[str] = None):
        """
        Load a world from a specific path.

        Args:
            world_path: Path to the world directory
            dimension: Dimension to load (defaults to get_settings().world_dimension)
        """
        try:
            if dimension is None:
                dimension = get_settings().world_dimension

            print(f"Loading world from: {world_path} (dimension: {dimension})")
            previous = self._world
            self._world = _open_world(world_path, dimension)
            self._world_path = world_path
            if previous is not None:
                previous.close()
            self._restart_workers()
            print(f"World loaded successfully from {world_path}")
            print(f"[WorldService] World instance updated: {self._world is not None}")
        except Exception as e:
            print(f"Failed to load world from {world_path}: {e}")
            raise

    def load_world_from_zip(self, zip_path: str, dimension: Optional[str] = None):
        """
        Extract a zip file containing a Minecraft world and load it.

        Args:
            zip_path: Path to the zip file
            dimension: Dimension to load (defaults to get_settings().world_dimension)

        Returns:
            Path to the extracted world directory
        """
        try:
            # Validate zip file
            if not zipfile.is_zipfile(zip_path):
                raise ValueError("The file is not a valid zip archive")

            # Check file size
            file_size = os.path.getsize(zip_path)
            max_size = get_settings().upload_max_size_mb * 1024 * 1024
            if file_size > max_size:
                raise ValueError(f"The zip file is too large ({file_size} bytes). The maximum is {max_size} bytes")

            # Create temp directory for extraction
            os.makedirs(get_settings().temp_world_dir, mode=0o700, exist_ok=True)
            temp_dir = tempfile.mkdtemp(dir=get_settings().temp_world_dir)

            print(f"Extracting world from {zip_path} to {temp_dir}")

            safe_extract(
                Path(zip_path),
                Path(temp_dir),
                max_entries=get_settings().upload_max_entries,
                max_total_bytes=get_settings().upload_max_unzipped_mb * 1024 * 1024,
                max_ratio=get_settings().upload_max_ratio,
            )

            # Find the world directory (could be at root or in a subdirectory)
            world_dir = self._find_world_directory(temp_dir)
            if not world_dir:
                raise ValueError("No valid Minecraft world found in the zip file")

            print(f"Found world directory: {world_dir}")

            # Load the world
            self.load_world_from_path(world_dir, dimension)

            # Clean up old temp worlds if needed
            if get_settings().cleanup_temp_files:
                self._cleanup_old_temp_worlds()

            return world_dir

        except Exception:
            # Clean up temp directory on failure
            if 'temp_dir' in locals():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def _find_world_directory(self, base_path: str) -> Optional[str]:
        """
        Find the Minecraft world directory within the extracted zip.
        Looks for a directory containing 'session.lock' or 'level.dat'.
        """
        for root, _dirs, files in os.walk(base_path):
            # Check if this directory contains world files
            if 'level.dat' in files or 'session.lock' in files:
                # Make sure it has a region directory (for overworld)
                region_path = os.path.join(root, 'region')
                if os.path.exists(region_path) and os.path.isdir(region_path):
                    return root

        # If not found, check if the base_path itself is a world directory
        if os.path.exists(os.path.join(base_path, 'level.dat')):
            return base_path

        return None

    def _cleanup_old_temp_worlds(self):
        """Clean up old temporary world directories."""
        try:
            if not os.path.exists(get_settings().temp_world_dir):
                return

            temp_dirs = [d for d in os.listdir(get_settings().temp_world_dir)
                        if os.path.isdir(os.path.join(get_settings().temp_world_dir, d))]

            if len(temp_dirs) > get_settings().max_temp_worlds:
                # Sort by modification time (oldest first)
                temp_dirs.sort(key=lambda d: os.path.getmtime(os.path.join(get_settings().temp_world_dir, d)))

                # Remove oldest directories
                dirs_to_remove = temp_dirs[:-get_settings().max_temp_worlds]
                for dir_name in dirs_to_remove:
                    dir_path = os.path.join(get_settings().temp_world_dir, dir_name)
                    print(f"Cleaning up old temp world: {dir_path}")
                    shutil.rmtree(dir_path, ignore_errors=True)

        except Exception as e:
            print(f"Error during cleanup: {e}")

    def get_world_info(self) -> Optional[WorldInfoResponse]:
        """Get world information using the library's method."""
        try:
            world_info_dict = self.world.get_world_info()
            if not world_info_dict:
                return None

            # Map anvil library fields to our response model
            mapped_info = {
                "dimension": world_info_dict.get("dimension", "overworld"),
                "world_folder": world_info_dict.get("world_folder", ""),
                "region_dir": world_info_dict.get("region_dir", ""),
                "bounds": world_info_dict.get("bounds"),
                "loaded_regions": world_info_dict.get("loaded_regions", 0),
                "region_list": world_info_dict.get("region_coordinates", []),
                "cache_stats": {
                    "cache_enabled": world_info_dict.get("cache_enabled", False),
                    "chunk_cache_size": world_info_dict.get("chunk_cache_size", 0),
                    "region_cache_size": world_info_dict.get("region_cache_size", 0)
                } if world_info_dict.get("cache_enabled") else None
            }

            return WorldInfoResponse(**mapped_info)
        except Exception as e:
            print(f"Error getting world info: {e}")
            return None

    def is_loaded(self) -> bool:
        """Check if world is loaded without triggering loading."""
        return self._world is not None

    def get_chunk_data(self, chunk_x: int, chunk_z: int, _chunk_h: int = 0, mode: str = 'heightmap') -> Optional[Union[ChunkDataResponse, IsometricChunkResponse]]:
        """
        Get chunk data in various formats.

        Args:
            chunk_x: Chunk X coordinate
            chunk_z: Chunk Z coordinate
            mode: Data format ('heightmap', 'surface', 'isometric', 'simplified', 'full')

        Returns:
            ChunkDataResponse (IsometricChunkResponse for the isometric mode) or None if chunk not found
        """
        try:
            try:
                chunk = self.world.get_chunk(chunk_x, chunk_z)
            except Exception:
                chunk = None

            if not isinstance(chunk, Chunk):
                return None

            if mode == "heightmap":
                try:
                    # Get heightmap (topmost solid blocks)
                    heightmap = []
                    for z in range(16):
                        height_row = []
                        for x in range(16):
                            # Find the highest solid block
                            height = 0
                            for y in range(320, -64, -1):  # From top to bottom
                                try:
                                    block = chunk.get_block(x, y, z, force_new=True)
                                    if block and block.name() not in ['minecraft:air', 'minecraft:cave_air', 'minecraft:void_air']:
                                        height = y
                                        break
                                except Exception:
                                    pass
                            height_row.append(height)
                        heightmap.append(height_row)

                    return ChunkDataResponse(
                        chunk_x=chunk_x,
                        chunk_z=chunk_z,
                        heightmap=heightmap,
                        surface_blocks=None,
                        sections=None,
                        palette=None
                    )
                except Exception as e:
                    print(f"Error generating heightmap for chunk ({chunk_x}, {chunk_z}): {e}")
                    traceback.print_exc()
                    return None

            elif mode == "surface":
                # Get surface blocks with biomes
                surface_blocks = []
                for z in range(16):
                    for x in range(16):
                        # Find the topmost solid block
                        for y in range(320, -64, -1):
                            try:
                                block = chunk.get_block(x, y, z, force_new=True)
                                if block and block.name() not in ['minecraft:air', 'minecraft:cave_air', 'minecraft:void_air']:
                                    # Get biome at this position
                                    global_x = chunk_x * 16 + x
                                    global_z = chunk_z * 16 + z
                                    biome = self.world.get_biome(global_x, y, global_z)

                                    surface_blocks.append({
                                        "x": global_x,
                                        "y": y,
                                        "z": global_z,
                                        "block": block.name(),
                                        "biome": biome.name() if biome else "unknown"
                                    })
                                    break
                            except Exception:
                                continue

                return ChunkDataResponse(
                    chunk_x=chunk_x,
                    chunk_z=chunk_z,
                    heightmap=None,
                    surface_blocks=surface_blocks,
                    sections=None,
                    palette=None
                )

            # Isometric mode: optimized block extraction for 2.5D view
            elif mode == "isometric":
                data = _isometric_chunk_data(self.world, chunk_x, chunk_z)
                return None if data is None else IsometricChunkResponse(**data)

            elif mode in ("simplified", "full"):
                # The library reads the sections; the palette is the block names they use.
                full = self.world.get_chunk_data(chunk_x, chunk_z, "full")
                if full is None:
                    return None
                sections = _plain(full["sections"])
                palette = sorted({entry["name"] for section in sections for entry in section.get("palette", [])})
                return ChunkDataResponse(
                    chunk_x=chunk_x,
                    chunk_z=chunk_z,
                    heightmap=None,
                    surface_blocks=None,
                    sections=sections if mode == "full" else None,
                    palette=palette
                )

        except Exception as e:
            print(f"Error getting chunk data: {e}")
            return None

    async def get_chunk_data_async(self, chunk_x: int, chunk_z: int, chunk_h: int = 0, mode: str = 'isometric'):
        """
        Get chunk data asynchronously using process pool.
        This allows multiple chunk requests to run in parallel instead of waiting for each other.

        Args:
            chunk_x: Chunk X coordinate
            chunk_z: Chunk Z coordinate
            chunk_h: Height parameter
            mode: Data format (currently only 'isometric' is optimized for async)

        Returns:
            ChunkDataResponse (IsometricChunkResponse for the isometric mode) or None if chunk not found
        """
        if mode != "isometric":
            # For other modes, fall back to synchronous version
            return self.get_chunk_data(chunk_x, chunk_z, chunk_h, mode)

        return (await self.get_isometric_chunk_timed(chunk_x, chunk_z))[0]

    async def get_isometric_chunk_timed(self, chunk_x: int, chunk_z: int) -> Tuple[Optional[IsometricChunkResponse], Dict[str, float]]:
        """
        Isometric chunk data from the process pool, with the time each phase took in milliseconds.

        Phases: ``queue``, ``world`` (only when the worker opens the world), ``chunk``, ``decode``,
        ``neighbours``, ``visibility``, ``project`` and ``return`` (from the worker finishing to the result being here).
        The returned dict also holds ``cold`` (1.0 if the worker opened the world for this
        request) and ``blocks`` (number of blocks sent). Both are notes rather than durations.
        """
        if not self.world_path:
            return None, {}

        loop = asyncio.get_event_loop()
        dimension = self.world.dimension if hasattr(self.world, 'dimension') else 'overworld'

        try:
            result, timings = await loop.run_in_executor(
                self._executor,
                _worker_get_chunk_isometric_timed,
                self.world_path,
                dimension,
                chunk_x,
                chunk_z,
                time.time()
            )
            timings["return"] = max(0.0, (time.time() - timings.pop("finished")) * 1000)

            if result is None:
                return None, timings

            timings["blocks"] = float(len(result["x"]))
            return IsometricChunkResponse(**result), timings
        except Exception as e:
            print(f"Async chunk data generation failed: {e}")
            return None, {}

    def get_area_heightmap(self, x1: int, z1: int, x2: int, z2: int) -> Optional[AreaHeightmapResponse]:
        """
        Get heightmap for an area.

        Args:
            x1, z1: Minimum block coordinates
            x2, z2: Maximum block coordinates

        Returns:
            Area heightmap dictionary
        """
        area_heightmap_dict = self.world.get_area_heightmap(x1, z1, x2, z2)
        return AreaHeightmapResponse(**area_heightmap_dict) if area_heightmap_dict else None

    def get_tile_data(self, tile_x: int, tile_z: int, tile_size: int = 16) -> Optional[TileDataResponse]:
        """
        Get tile data for progressive loading.

        Args:
            tile_x: Tile X coordinate
            tile_z: Tile Z coordinate
            tile_size: Number of chunks per tile side

        Returns:
            Tile data dictionary with all chunks
        """
        tile_data_dict = self.world.get_tile_data(tile_x, tile_z, tile_size)
        return TileDataResponse(**tile_data_dict) if tile_data_dict else None

    def get_block_data(self, block_x: int, block_y: int, block_z: int) -> Optional[BlockDataResponse]:
        """
        Get block data at specified coordinates.

        Args:
            block_x: Block X coordinate
            block_y: Block Y coordinate
            block_z: Block Z coordinate

        Returns:
            Block data dictionary or None if block not found
        """
        block = self.world.get_block(block_x, block_y, block_z)
        if block is None:
            return None
        if isinstance(block, OldBlock):
            block = block.convert()
        return BlockDataResponse(
            block_x=block_x,
            block_y=block_y,
            block_z=block_z,
            id=str(block.id),
            properties={str(key): str(value) for key, value in block.properties.items()},
        )

    def get_biome_data(self, biome_x: int, biome_y: int, biome_z: int) -> Optional[BiomeDataResponse]:
        """
        Get biome data at specified coordinates.

        Args:
            biome_x: Biome X coordinate
            biome_z: Biome Z coordinate

        Returns:
            Biome data dictionary or None if biome not found
        """
        biome = self.world.get_biome(biome_x, biome_y, biome_z)
        if biome is None:
            return None
        return BiomeDataResponse(biome_x=biome_x, biome_y=biome_y, biome_z=biome_z, id=str(biome.id))

def _plain(value):
    """`value` with NBT tags replaced by their Python values, so that it can be sent as JSON."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _plain(value.value) if hasattr(value, "value") else str(value)


_world_service: Optional[WorldService] = None


def get_world_service() -> WorldService:
    """
    Get the global WorldService instance.
    Used as a dependency in FastAPI endpoints.
    """
    global _world_service
    if _world_service is None:
        _world_service = WorldService()
    return _world_service
