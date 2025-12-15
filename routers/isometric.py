"""
Isometric Viewer API - All Blocks Extraction
=============================================
Retrieves ALL non-air blocks from one or more chunks.
Modes: single (1 chunk), radius (multiple), list, all (entire map)
"""

import asyncio
import logging
import time
import os
import gc
from typing import Dict, List, Optional, Tuple, Any, NamedTuple
from concurrent.futures import ProcessPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Query
from models.responses import APIResponse
from services.world_service import WorldService, get_world_service
from anvil import World

try:
    from anvil.empty_chunk import EmptyChunk
except ImportError:
    EmptyChunk = type('EmptyChunk', (), {})

logger = logging.getLogger(__name__)

# Air blocks to ignore
AIR_BLOCKS = frozenset({'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air', None, ''})

# Transparent blocks (exact matches for backward compatibility)
TRANSPARENT_BLOCKS = frozenset({
    'minecraft:glass', 'minecraft:glass_pane', 'minecraft:water', 'minecraft:ice',
    'minecraft:oak_leaves', 'minecraft:spruce_leaves', 'minecraft:birch_leaves',
    'minecraft:jungle_leaves', 'minecraft:acacia_leaves', 'minecraft:dark_oak_leaves',
    'minecraft:azalea_leaves', 'minecraft:flowering_azalea_leaves', 'minecraft:mangrove_leaves',
    'minecraft:cherry_leaves', 'minecraft:tall_grass', 'minecraft:short_grass',
    'minecraft:fern', 'minecraft:large_fern', 'minecraft:vine', 'minecraft:torch',
})

# Transparent block patterns (partial matches for flexibility)
TRANSPARENT_PATTERNS = ('glass', 'leaves', 'water', 'ice', 'tall_grass', 'short_grass', 
                        'fern', 'vine', 'torch', 'flower', 'sapling')

def is_transparent(block_name: str) -> bool:
    """Check if a block is transparent (flexible pattern matching)."""
    if not block_name:
        return True
    if block_name in TRANSPARENT_BLOCKS:
        return True
    name_lower = block_name.lower()
    return any(pattern in name_lower for pattern in TRANSPARENT_PATTERNS)


class BlockData(NamedTuple):
    """Lightweight structure for a block with global coordinates."""
    x: int
    y: int
    z: int
    block: str
    biome: str

    def to_dict(self):
        return {"x": self.x, "y": self.y, "z": self.z, "block": self.block, "biome": self.biome}


class ChunkData(NamedTuple):
    """Chunk data with all its blocks."""
    chunk_x: int
    chunk_z: int
    blocks: List[BlockData]
    bounds: Tuple[int, int, int, int]  # min_x, max_x, min_z, max_z


def _worker_extract_all_blocks(world_path: str, dimension: str, cx: int, cz: int, min_y: int, max_y: int) -> ChunkData:
    """
    Worker function to extract blocks from a chunk.
    Running in a separate process, so it must instantiate its own World access.
    """
    try:
        # Re-instantiate World for this process
        world = World(world_path, dimension=dimension)
        
        blocks = []
        chunk = world.get_chunk(cx, cz)
        
        if not chunk or isinstance(chunk, EmptyChunk):
            return ChunkData(cx, cz, [], (cx*16, cx*16+15, cz*16, cz*16+15))
        
        min_scan = max(min_y, -64)
        max_scan = min(max_y, 319)
        
        # Optimization: Scan by Section (16x16x16)
        min_section_y = min_scan // 16
        max_section_y = max_scan // 16
        
        for sy in range(min_section_y, max_section_y + 1):
            section = chunk.get_section(sy)
            if section is None:
                continue
            
            # Smart Skip: Check Palette
            palette = chunk.get_palette(section)
            if not palette:
                continue
                
            # If all blocks in palette are Air/Ignored, skip the whole section
            is_empty_section = True
            for block_type in palette:
                name = block_type.name()
                if name not in AIR_BLOCKS:
                    is_empty_section = False
                    break
            
            if is_empty_section:
                continue
                
            # Iterate only within this section's Y range constrained by request
            y_start = max(sy * 16, min_scan)
            y_end = min((sy + 1) * 16 - 1, max_scan)
            
            for y in range(y_start, y_end + 1):
                for lx in range(16):
                    for lz in range(16):
                        try:
                            block = chunk.get_block(lx, y, lz)
                            if block:
                                name = block.name()
                                if name and name not in AIR_BLOCKS:
                                    gx, gz = cx * 16 + lx, cz * 16 + lz
                                    try:
                                        biome = world.get_biome(gx, y, gz)
                                        biome_name = biome.name() if biome else "minecraft:plains"
                                    except:
                                        biome_name = "minecraft:plains"
                                    
                                    blocks.append(BlockData(gx, y, gz, name, biome_name))
                        except:
                            continue

        return ChunkData(cx, cz, blocks, (cx*16, cx*16+15, cz*16, cz*16+15))
        
    except Exception as e:
        logger.warning(f"Failed chunk {cx},{cz}: {e}")
        return ChunkData(cx, cz, [], (cx*16, cx*16+15, cz*16, cz*16+15))


def _worker_extract_surface_blocks(world_path: str, dimension: str, cx: int, cz: int) -> List[BlockData]:
    """
    Worker for extracting surface blocks (optimized).
    """
    try:
        world = World(world_path, dimension=dimension)
        blocks = []
        chunk = world.get_chunk(cx, cz)
        
        if not chunk or isinstance(chunk, EmptyChunk):
            return []
        
        # Load relevant blocks into a map first (sparse loading)
        chunk_blocks = {}
        
        # We scan all relevant sections
        for sy in range(-4, 20): # -64 to 319 range roughly
            section = chunk.get_section(sy)
            if section is None:
                continue
                
            palette = chunk.get_palette(section)
            if not palette:
                continue
                
            is_empty = True
            for b in palette:
                if b.name() not in AIR_BLOCKS:
                    is_empty = False
                    break
            
            if is_empty:
                continue
                
            # Read blocks in this section
            base_y = sy * 16
            for y in range(base_y, base_y + 16):
                if y < -64 or y > 319: continue
                
                for lx in range(16):
                    for lz in range(16):
                        try:
                            block = chunk.get_block(lx, y, lz)
                            # Only store non-air blocks to save memory
                            if block and block.name() not in AIR_BLOCKS:
                                chunk_blocks[(lx, y, lz)] = block.name()
                        except:
                            pass
                            
        # Now apply visibility logic using the map
        directions = [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]
        
        for (lx, y, lz), block_name in chunk_blocks.items():
            gx, gz = cx * 16 + lx, cz * 16 + lz
            has_exposed_face = False
            
            for dx, dy, dz in directions:
                nx, ny, nz = lx + dx, y + dy, lz + dz
                
                if ny < -64 or ny > 319:
                    has_exposed_face = True
                    break
                if nx < 0 or nx >= 16 or nz < 0 or nz >= 16:
                    has_exposed_face = True
                    break
                    
                neighbor = chunk_blocks.get((nx, ny, nz))
                # If neighbor is missing (air) or transparent
                if neighbor is None or neighbor in TRANSPARENT_BLOCKS:
                    has_exposed_face = True
                    break
            
            if block_name in TRANSPARENT_BLOCKS:
                has_exposed_face = True
                
            if has_exposed_face:
                try:
                    biome = world.get_biome(gx, y, gz)
                    biome_name = biome.name() if biome else "minecraft:plains"
                except:
                    biome_name = "minecraft:plains"
                
                blocks.append(BlockData(gx, y, gz, block_name, biome_name))
                
        return blocks
        
    except Exception as e:
        logger.warning(f"Surface extraction failed for {cx},{cz}: {e}")
        return []


class IsometricService:
    """Service for extracting all blocks for isometric view."""
    
    MAX_CACHE_SIZE = 256
    
    def __init__(self, max_workers: int = 8):
        # Use ProcessPoolExecutor for true parallelism bypassing GIL
        self.executor = ProcessPoolExecutor(max_workers=max_workers)
        self._cache: Dict[str, ChunkData] = {}
        self._cache_order: List[str] = []
        self._cache_lock = asyncio.Lock()
        self._stats = {"cache_hits": 0, "cache_misses": 0, "chunks_processed": 0, "blocks_found": 0}

    async def get_all_blocks(
        self,
        world_service: WorldService,
        chunk_coords: List[Tuple[int, int]],
        min_y: int = -64,
        max_y: int = 319
    ) -> Dict[str, Any]:
        """Retrieves all blocks from specified chunks."""
        start = time.time()
        unique_coords = list(set(chunk_coords))
        
        # Parallel processing of chunks
        path = world_service.world_path
        # Defensive check for dimension
        dim = 'overworld'
        if hasattr(world_service.world, 'dimension'):
            dim = world_service.world.dimension
        
        tasks = [self._process_chunk(path, dim, cx, cz, min_y, max_y) for cx, cz in unique_coords]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        all_blocks = []
        valid_chunks = 0
        bounds = [float('inf'), float('-inf'), float('inf'), float('-inf'), float('inf'), float('-inf')]
        
        for res in results:
            if isinstance(res, Exception):
                logger.warning(f"Chunk error: {res}")
                continue
            if res and res.blocks:
                valid_chunks += 1
                all_blocks.extend(res.blocks)
                bounds[0] = min(bounds[0], res.bounds[0])
                bounds[1] = max(bounds[1], res.bounds[1])
                bounds[4] = min(bounds[4], res.bounds[2])
                bounds[5] = max(bounds[5], res.bounds[3])
        
        # Calculate Y bounds
        if all_blocks:
            bounds[2] = min(b.y for b in all_blocks)
            bounds[3] = max(b.y for b in all_blocks)
        else:
            bounds = [0, 0, 0, 0, 0, 0]
        
        elapsed = int((time.time() - start) * 1000)
        self._stats["chunks_processed"] += valid_chunks
        self._stats["blocks_found"] += len(all_blocks)
        
        return {
            "blocks": [b.to_dict() for b in all_blocks],
            "total_blocks": len(all_blocks),
            "chunks_loaded": valid_chunks,
            "bounds": {
                "min_x": int(bounds[0]) if bounds[0] != float('inf') else 0,
                "max_x": int(bounds[1]) if bounds[1] != float('-inf') else 0,
                "min_y": int(bounds[2]),
                "max_y": int(bounds[3]),
                "min_z": int(bounds[4]) if bounds[4] != float('inf') else 0,
                "max_z": int(bounds[5]) if bounds[5] != float('-inf') else 0
            },
            "time_ms": elapsed,
            "cache_hit_rate": self._get_cache_hit_rate()
        }

    async def _process_chunk(self, world_path: str, dimension: str, cx: int, cz: int, min_y: int, max_y: int) -> ChunkData:
        """Process a chunk with LRU caching."""
        cache_key = f"{cx}_{cz}_{min_y}_{max_y}"
        
        async with self._cache_lock:
            if cache_key in self._cache:
                self._stats["cache_hits"] += 1
                self._cache_order.remove(cache_key)
                self._cache_order.append(cache_key)
                return self._cache[cache_key]
        
        self._stats["cache_misses"] += 1
        
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                self.executor, _worker_extract_all_blocks, world_path, dimension, cx, cz, min_y, max_y
            )
            
            async with self._cache_lock:
                while len(self._cache) >= self.MAX_CACHE_SIZE and self._cache_order:
                    old = self._cache_order.pop(0)
                    self._cache.pop(old, None)
                self._cache[cache_key] = data
                self._cache_order.append(cache_key)
            
            return data
        except Exception as e:
            logger.error(f"Chunk process dispatch {cx},{cz} failed: {e}")
            return ChunkData(cx, cz, [], (cx*16, cx*16+15, cz*16, cz*16+15))

    def scan_all_regions(self, world_service: WorldService) -> List[Tuple[int, int]]:
        """Scans all regions and returns chunk coordinates."""
        region_dir = os.path.join(world_service.world_path, "region")
        if not os.path.exists(region_dir):
            return []
        
        chunks = []
        for filename in os.listdir(region_dir):
            if filename.endswith(".mca") and filename.startswith("r."):
                parts = filename.split(".")
                if len(parts) >= 4:
                    try:
                        rx, rz = int(parts[1]), int(parts[2])
                        for cx in range(rx * 32, rx * 32 + 32):
                            for cz in range(rz * 32, rz * 32 + 32):
                                chunks.append((cx, cz))
                    except ValueError:
                        continue
        return chunks

    def _get_cache_hit_rate(self) -> str:
        total = self._stats["cache_hits"] + self._stats["cache_misses"]
        return f"{(self._stats['cache_hits'] / total * 100):.1f}%" if total > 0 else "0%"

    async def clear_cache(self):
        async with self._cache_lock:
            self._cache.clear()
            self._cache_order.clear()
            gc.collect()


# Global instance
_service = None

def get_isometric_service():
    global _service
    if _service is None:
        _service = IsometricService()
    return _service


# === ROUTER ===
router = APIRouter(prefix="/api/isometric", tags=["isometric"])


@router.get("/blocks")
async def get_blocks(
    mode: str = Query("radius", description="Mode: 'radius', 'list', 'all'"),
    center_x: int = Query(0, description="Center X (chunk coords)"),
    center_z: int = Query(0, description="Center Z (chunk coords)"),
    radius: int = Query(2, ge=0, le=16, description="Radius in chunks (0 = single chunk)"),
    chunk_list: Optional[str] = Query(None, description="List: 'x,z;x,z;...'"),
    min_y: int = Query(-64, description="Y minimum"),
    max_y: int = Query(319, description="Y maximum"),
    limit: int = Query(1024, description="Chunk limit"),
    world_service: WorldService = Depends(get_world_service),
    iso_service: IsometricService = Depends(get_isometric_service)
):
    """
    Retrieves ALL non-air blocks from selected chunks.
    
    **Modes:**
    - `radius`: Chunks around (center_x, center_z) with specified radius
    - `list`: Explicit list of chunks (format: "0,0;1,0;1,1")
    - `all`: All chunks in the map (warning: can be very heavy!)
    
    **Examples:**
    - 1 chunk: `?mode=radius&center_x=0&center_z=0&radius=0`
    - 5x5 area: `?mode=radius&center_x=0&center_z=0&radius=2`
    - List: `?mode=list&chunk_list=0,0;0,1;1,0`
    - Entire map: `?mode=all&limit=500`
    """
    if not world_service.is_loaded():
        raise HTTPException(503, "World not loaded. Upload a world first.")
    
    chunks = []
    
    if mode == "radius":
        for cx in range(center_x - radius, center_x + radius + 1):
            for cz in range(center_z - radius, center_z + radius + 1):
                chunks.append((cx, cz))
    
    elif mode == "list":
        if not chunk_list:
            raise HTTPException(400, "Mode 'list' requires chunk_list parameter")
        for pair in chunk_list.split(";"):
            pair = pair.strip()
            if "," in pair:
                try:
                    x, z = map(int, pair.split(","))
                    chunks.append((x, z))
                except ValueError:
                    raise HTTPException(400, f"Invalid chunk coord: {pair}")
    
    elif mode == "all":
        chunks = iso_service.scan_all_regions(world_service)
    
    else:
        raise HTTPException(400, f"Unknown mode: {mode}. Use 'radius', 'list', or 'all'")
    
    # Apply limit
    total_requested = len(chunks)
    if total_requested > limit:
        chunks = chunks[:limit]
        logger.warning(f"Truncated {total_requested} chunks to {limit}")
    
    if not chunks:
        return APIResponse(status="success", data={
            "blocks": [], "total_blocks": 0, "chunks_loaded": 0,
            "bounds": {"min_x": 0, "max_x": 0, "min_y": 0, "max_y": 0, "min_z": 0, "max_z": 0}
        })
    
    result = await iso_service.get_all_blocks(world_service, chunks, min_y, max_y)
    result["selection"] = {
        "mode": mode,
        "requested_chunks": total_requested,
        "processed_chunks": len(chunks),
        "limit_applied": total_requested > limit
    }
    
    return APIResponse(status="success", data=result)


@router.get("/surface")
async def get_surface_blocks(
    mode: str = Query("radius", description="Mode: 'radius', 'list', 'all'"),
    center_x: int = Query(0, description="Center X (chunk coords)"),
    center_z: int = Query(0, description="Center Z (chunk coords)"),
    radius: int = Query(2, ge=0, le=32, description="Radius in chunks"),
    chunk_list: Optional[str] = Query(None, description="List: 'x,z;x,z;...'"),
    limit: int = Query(2048, description="Chunk limit"),
    world_service: WorldService = Depends(get_world_service),
    iso_service: IsometricService = Depends(get_isometric_service)
):
    """
    Retrieves only SURFACE BLOCKS (the highest block at each X,Z).
    Much lighter than /blocks - ideal for isometric view.
    
    Also returns the bounds of the visible world.
    """
    if not world_service.is_loaded():
        raise HTTPException(503, "World not loaded")
    
    # Determine chunks to load
    chunks = []
    if mode == "radius":
        for cx in range(center_x - radius, center_x + radius + 1):
            for cz in range(center_z - radius, center_z + radius + 1):
                chunks.append((cx, cz))
    elif mode == "list":
        if not chunk_list:
            raise HTTPException(400, "Mode 'list' requires chunk_list")
        for pair in chunk_list.split(";"):
            pair = pair.strip()
            if "," in pair:
                try:
                    x, z = map(int, pair.split(","))
                    chunks.append((x, z))
                except ValueError:
                    pass
    elif mode == "all":
        chunks = iso_service.scan_all_regions(world_service)
    
    total_requested = len(chunks)
    if total_requested > limit:
        chunks = chunks[:limit]
    
    if not chunks:
        return APIResponse(status="success", data={
            "blocks": [], "total_blocks": 0, "chunks_loaded": 0,
            "bounds": {"min_x": 0, "max_x": 0, "min_y": 0, "max_y": 0, "min_z": 0, "max_z": 0}
        })
    
    start = time.time()
    
    path = world_service.world_path
    dim = 'overworld'
    if hasattr(world_service.world, 'dimension'):
        dim = world_service.world.dimension

    # Extract all non-air blocks from all chunks
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(iso_service.executor, _worker_extract_surface_blocks, path, dim, cx, cz)
        for cx, cz in chunks
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Aggregate all blocks
    all_raw_blocks: List[BlockData] = []
    valid_chunks = 0
    
    for res in results:
        if isinstance(res, Exception):
            continue
        if res:
            valid_chunks += 1
            all_raw_blocks.extend(res)
    
    # Apply optimized isometric culling
    visible_blocks = _apply_global_culling(all_raw_blocks)
    
    # Convert to dict and compute bounds
    all_blocks = []
    min_x, max_x = float('inf'), float('-inf')
    min_y, max_y = float('inf'), float('-inf')
    min_z, max_z = float('inf'), float('-inf')
    
    for b in visible_blocks:
        all_blocks.append(b.to_dict())
        min_x, max_x = min(min_x, b.x), max(max_x, b.x)
        min_y, max_y = min(min_y, b.y), max(max_y, b.y)
        min_z, max_z = min(min_z, b.z), max(max_z, b.z)
    
    elapsed = int((time.time() - start) * 1000)
    logger.info(f"Surface: {len(all_raw_blocks)} raw -> {len(visible_blocks)} visible ({valid_chunks} chunks, {elapsed}ms)")
    
    return APIResponse(status="success", data={
        "blocks": all_blocks,
        "total_blocks": len(all_blocks),
        "chunks_loaded": valid_chunks,
        "bounds": {
            "min_x": int(min_x) if min_x != float('inf') else 0,
            "max_x": int(max_x) if max_x != float('-inf') else 0,
            "min_y": int(min_y) if min_y != float('inf') else 0,
            "max_y": int(max_y) if max_y != float('-inf') else 0,
            "min_z": int(min_z) if min_z != float('inf') else 0,
            "max_z": int(max_z) if max_z != float('-inf') else 0
        },
        "time_ms": elapsed,
        "selection": {
            "mode": mode,
            "requested_chunks": total_requested,
            "processed_chunks": len(chunks),
            "limit_applied": total_requested > limit
        }
    })


def _apply_global_culling(blocks: List[BlockData]) -> List[BlockData]:
    """
    Optimized isometric surface culling.
    """
    if not blocks:
        return []
    
    # Build position lookup
    block_map = {(b.x, b.y, b.z): b.block for b in blocks}
    
    # Step 1: Find highest solid block per column - surface level
    columns: dict = {}  # (x,z) -> highest_y
    for b in blocks:
        if not is_transparent(b.block):
            key = (b.x, b.z)
            if key not in columns or b.y > columns[key]:
                columns[key] = b.y
    
    visible = []
    seen = set()
    
    # Depth: how many blocks below surface to include (for terrain depth)
    SURFACE_DEPTH = 3
    
    # Directions for isometric camera at (+X, +Y, +Z)
    iso_directions = [(0, 1, 0), (1, 0, 0), (0, 0, 1)]
    
    for b in blocks:
        pos = (b.x, b.y, b.z)
        if pos in seen:
            continue
            
        include = False
        highest_y = columns.get((b.x, b.z), -999)
        
        # Rule 1: Transparent blocks always visible
        if is_transparent(b.block):
            include = True
        
        # Rule 2: Blocks within SURFACE_DEPTH of the highest = visible surface
        elif b.y >= highest_y - SURFACE_DEPTH:
            include = True
        
        # Rule 3: Deeper blocks - only if isometric face exposed (caves, cliffs)
        else:
            for dx, dy, dz in iso_directions:
                neighbor = block_map.get((b.x + dx, b.y + dy, b.z + dz))
                if neighbor is None or is_transparent(neighbor):
                    include = True
                    break
        
        if include:
            visible.append(b)
            seen.add(pos)
    
    return visible


@router.post("/cache/clear")
async def clear_cache(iso_service: IsometricService = Depends(get_isometric_service)):
    """Clear the chunk cache."""
    await iso_service.clear_cache()
    return APIResponse(status="success", data={"message": "Cache cleared"})


@router.get("/stats")
async def get_stats(iso_service: IsometricService = Depends(get_isometric_service)):
    """Service statistics."""
    return APIResponse(status="success", data=iso_service._stats)
