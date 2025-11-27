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
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Query
from models.responses import APIResponse
from services.world_service import WorldService, get_world_service

try:
    from anvil.empty_chunk import EmptyChunk
except ImportError:
    EmptyChunk = type('EmptyChunk', (), {})

logger = logging.getLogger(__name__)

# Air blocks to ignore
AIR_BLOCKS = frozenset({'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air', None, ''})

# Transparent blocks that don't block visibility
TRANSPARENT_BLOCKS = frozenset({
    'minecraft:glass', 'minecraft:glass_pane', 'minecraft:water', 'minecraft:ice', 'minecraft:frosted_ice',
    'minecraft:oak_leaves', 'minecraft:spruce_leaves', 'minecraft:birch_leaves',
    'minecraft:jungle_leaves', 'minecraft:acacia_leaves', 'minecraft:dark_oak_leaves',
    'minecraft:azalea_leaves', 'minecraft:flowering_azalea_leaves', 'minecraft:mangrove_leaves',
    'minecraft:cherry_leaves', 'minecraft:tall_grass', 'minecraft:grass', 'minecraft:short_grass',
    'minecraft:fern', 'minecraft:large_fern', 'minecraft:vine', 'minecraft:torch', 'minecraft:wall_torch',
    'minecraft:flower', 'minecraft:dandelion', 'minecraft:poppy', 'minecraft:blue_orchid',
    'minecraft:allium', 'minecraft:azure_bluet', 'minecraft:red_tulip', 'minecraft:orange_tulip',
    'minecraft:white_tulip', 'minecraft:pink_tulip', 'minecraft:oxeye_daisy', 'minecraft:cornflower',
    'minecraft:lily_of_the_valley', 'minecraft:sunflower', 'minecraft:lilac', 'minecraft:rose_bush',
    'minecraft:peony', 'minecraft:cobweb', 'minecraft:ladder', 'minecraft:rail', 'minecraft:powered_rail',
    'minecraft:detector_rail', 'minecraft:activator_rail', 'minecraft:iron_bars', 'minecraft:chain',
})


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


class IsometricService:
    """Service for extracting all blocks for isometric view."""
    
    MAX_CACHE_SIZE = 256
    
    def __init__(self, max_workers: int = 8):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="iso")
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
        tasks = [self._process_chunk(world_service, cx, cz, min_y, max_y) for cx, cz in unique_coords]
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

    async def _process_chunk(self, world_service, cx: int, cz: int, min_y: int, max_y: int) -> ChunkData:
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
                self.executor, self._extract_all_blocks, world_service, cx, cz, min_y, max_y
            )
            
            async with self._cache_lock:
                # LRU eviction if cache full
                while len(self._cache) >= self.MAX_CACHE_SIZE and self._cache_order:
                    old = self._cache_order.pop(0)
                    self._cache.pop(old, None)
                self._cache[cache_key] = data
                self._cache_order.append(cache_key)
            
            return data
        except Exception as e:
            logger.error(f"Chunk {cx},{cz} failed: {e}")
            return ChunkData(cx, cz, [], (cx*16, cx*16+15, cz*16, cz*16+15))

    @staticmethod
    def _extract_all_blocks(world_service, cx: int, cz: int, min_y: int, max_y: int) -> ChunkData:
        """Extracts ALL non-air blocks from a chunk (synchronous)."""
        blocks = []
        
        try:
            chunk = world_service.world.get_chunk(cx, cz)
            if not chunk or isinstance(chunk, EmptyChunk):
                return ChunkData(cx, cz, [], (cx*16, cx*16+15, cz*16, cz*16+15))
            
            min_scan = max(min_y, -64)
            max_scan = min(max_y, 319)
            
            for lx in range(16):
                for lz in range(16):
                    gx, gz = cx * 16 + lx, cz * 16 + lz
                    
                    for y in range(min_scan, max_scan + 1):
                        try:
                            block = chunk.get_block(lx, y, lz)
                            if block:
                                name = block.name()
                                if name and name not in AIR_BLOCKS:
                                    # Biome (fallback on error)
                                    try:
                                        biome = world_service.world.get_biome(gx, y, gz)
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
_service = IsometricService()
def get_isometric_service(): return _service


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
    
    # Extract all non-air blocks from all chunks
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(iso_service.executor, _extract_all_blocks_simple, world_service, cx, cz)
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
    
    # Now apply culling on the aggregated blocks (global view)
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


def _extract_all_blocks_simple(world_service, cx: int, cz: int) -> List[BlockData]:
    """Extract all non-air blocks from a chunk (no culling)."""
    blocks = []
    try:
        chunk = world_service.world.get_chunk(cx, cz)
        if not chunk or isinstance(chunk, EmptyChunk):
            return []
        
        for lx in range(16):
            for lz in range(16):
                gx, gz = cx * 16 + lx, cz * 16 + lz
                for y in range(-64, 320):
                    try:
                        block = chunk.get_block(lx, y, lz)
                        if block:
                            name = block.name()
                            if name and name not in AIR_BLOCKS:
                                try:
                                    biome = world_service.world.get_biome(gx, y, gz)
                                    biome_name = biome.name() if biome else "minecraft:plains"
                                except:
                                    biome_name = "minecraft:plains"
                                blocks.append(BlockData(gx, y, gz, name, biome_name))
                    except:
                        continue
        return blocks
    except Exception as e:
        logger.warning(f"Extract failed for chunk {cx},{cz}: {e}")
        return []


def _apply_global_culling(blocks: List[BlockData]) -> List[BlockData]:
    """Apply visibility culling on aggregated blocks (global view)."""
    if not blocks:
        return []
    
    # Build position lookup
    block_map = {(b.x, b.y, b.z): b.block for b in blocks}
    
    visible = []
    directions = [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]
    
    for b in blocks:
        # Transparent blocks are always visible
        if b.block in TRANSPARENT_BLOCKS:
            visible.append(b)
            continue
        
        # Check if at least one face is exposed
        has_exposed = False
        for dx, dy, dz in directions:
            neighbor_pos = (b.x + dx, b.y + dy, b.z + dz)
            neighbor = block_map.get(neighbor_pos)
            
            # Exposed if no neighbor OR neighbor is transparent/air
            if neighbor is None or neighbor in TRANSPARENT_BLOCKS or neighbor in AIR_BLOCKS:
                has_exposed = True
                break
        
        if has_exposed:
            visible.append(b)
    
    return visible


def _extract_surface_blocks(world_service, cx: int, cz: int) -> List[BlockData]:
    """
    Extracts VISIBLE blocks from a chunk.
    A block is visible if it has at least one exposed face (adjacent to air or transparent).
    Includes: terrain surface, trees, flowers, cave entrances, cliffs...
    """
    blocks = []
    
    try:
        chunk = world_service.world.get_chunk(cx, cz)
        if not chunk or isinstance(chunk, EmptyChunk):
            return []
        
        # Pre-load all chunk blocks into a dict for fast access
        chunk_blocks = {}
        for lx in range(16):
            for lz in range(16):
                for y in range(-64, 320):
                    try:
                        block = chunk.get_block(lx, y, lz)
                        if block:
                            name = block.name()
                            if name and name not in AIR_BLOCKS:
                                chunk_blocks[(lx, y, lz)] = name
                    except:
                        continue
        
        # For each non-air block, check if it has an exposed face
        directions = [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]
        
        for (lx, y, lz), block_name in chunk_blocks.items():
            gx, gz = cx * 16 + lx, cz * 16 + lz
            
            # Check if at least one face is exposed
            has_exposed_face = False
            
            for dx, dy, dz in directions:
                nx, ny, nz = lx + dx, y + dy, lz + dz
                
                # Out of Y bounds = exposed
                if ny < -64 or ny > 319:
                    has_exposed_face = True
                    break
                
                # Outside chunk = assume exposed (simplifies code)
                if nx < 0 or nx >= 16 or nz < 0 or nz >= 16:
                    has_exposed_face = True
                    break
                
                # Neighbor = air or transparent = face exposed
                neighbor = chunk_blocks.get((nx, ny, nz))
                if neighbor is None or neighbor in TRANSPARENT_BLOCKS:
                    has_exposed_face = True
                    break
            
            # Transparent blocks are always visible (leaves, flowers, etc.)
            if block_name in TRANSPARENT_BLOCKS:
                has_exposed_face = True
            
            if has_exposed_face:
                try:
                    biome = world_service.world.get_biome(gx, y, gz)
                    biome_name = biome.name() if biome else "minecraft:plains"
                except:
                    biome_name = "minecraft:plains"
                
                blocks.append(BlockData(gx, y, gz, block_name, biome_name))
        
        return blocks
        
    except Exception as e:
        logger.warning(f"Surface extraction failed for {cx},{cz}: {e}")
        return []


@router.post("/cache/clear")
async def clear_cache(iso_service: IsometricService = Depends(get_isometric_service)):
    """Clear the chunk cache."""
    await iso_service.clear_cache()
    return APIResponse(status="success", data={"message": "Cache cleared"})


@router.get("/stats")
async def get_stats(iso_service: IsometricService = Depends(get_isometric_service)):
    """Service statistics."""
    return APIResponse(status="success", data=iso_service._stats)
