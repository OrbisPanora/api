"""
Chunk endpoints for the API.
Provides chunk data in various formats for the isometric viewer.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.responses import (
    APIResponse,
    AreaHeightmapResponse,
    ChunkDataResponse,
    TileDataResponse,
)
from ..services.world_service import WorldService, get_world_service
from ..utils.errors import WorldNotLoadedError

LOGGER = logging.getLogger(__name__)

#: Largest side of an area heightmap, in blocks.
MAX_AREA_SIDE = 1024

router = APIRouter(
    prefix="/api/chunks",
    tags=["chunks"],
    responses={
        404: {"description": "Chunk not found"},
        400: {"description": "Invalid parameters"},
        503: {"description": "World not loaded"},
        500: {"description": "Internal server error"}
    }
)


@router.get(
    "/viewport/render",
    response_model=APIResponse[dict],
    summary="Get pre-calculated viewport render data",
    description="Returns optimized render data for a viewport area with pre-calculated isometric positions and sprites.",
    status_code=200
)
async def get_viewport_render(
    center_x: int = Query(..., description="Center chunk X coordinate"),
    center_z: int = Query(..., description="Center chunk Z coordinate"),
    view_distance: int = Query(4, ge=1, le=32, description="View distance in chunks (1-16)"),
    world_service: WorldService = Depends(get_world_service)
) -> APIResponse[dict]:
    """
    Get pre-calculated render data for a viewport area.

    This endpoint optimizes performance by:
    - Loading only visible chunks based on view distance
    - Pre-calculating all isometric positions and sprites
    - Sorting blocks for correct rendering order
    - Providing viewport bounds for culling

    **Parameters:**
    - center_x, center_z: Center chunk coordinates
    - view_distance: Number of chunks to load in each direction (max 16)

    **Returns:**
    - chunks: Array of render data for each chunk
    - viewport_bounds: Screen bounds for the entire viewport
    - total_blocks: Total number of blocks to render
    - load_time_ms: Server-side processing time

    **Performance optimizations:**
    - Lazy loading: Only loads chunks within view distance
    - Pre-calculated positions: No client-side math required
    - Sprite batching: Optimized texture lookups
    - Viewport culling: Bounds for efficient rendering
    """
    try:
        if not world_service.is_loaded():
            raise WorldNotLoadedError()

        print("[DEBUG] World is loaded, processing real data...")

        start_time = time.time()

        print(f"[DEBUG] Viewport render request: center=({center_x},{center_z}), view_distance={view_distance}")

        # Calculate viewport bounds
        min_chunk_x = center_x - view_distance
        max_chunk_x = center_x + view_distance
        min_chunk_z = center_z - view_distance
        max_chunk_z = center_z + view_distance

        print(f"[DEBUG] Chunk range: x=[{min_chunk_x},{max_chunk_x}], z=[{min_chunk_z},{max_chunk_z}]")

        chunks_data = []
        all_sprites = {}
        # Initialize with proper defaults instead of infinity
        viewport_min_x = 0
        viewport_max_x = 0
        viewport_min_y = 0
        viewport_max_y = 0
        total_blocks = 0
        chunks_with_blocks = 0

        # Load all chunks in viewport
        # Load all chunks in viewport asynchronously
        tasks = []
        for chunk_x in range(min_chunk_x, max_chunk_x + 1):
            for chunk_z in range(min_chunk_z, max_chunk_z + 1):
                tasks.append(world_service.get_render_data_async(chunk_x, chunk_z))

        print("[DEBUG] Ensuring gathered tasks...")
        results = await asyncio.gather(*tasks)

        # Process results
        task_idx = 0
        for chunk_x in range(min_chunk_x, max_chunk_x + 1):
            for chunk_z in range(min_chunk_z, max_chunk_z + 1):
                chunk_render_data = results[task_idx]
                task_idx += 1

                # Verify data structure
                if not chunk_render_data:
                    continue

                if chunk_render_data.get("blocks"):
                    chunks_data.append({
                        "chunk_x": chunk_x,
                        "chunk_z": chunk_z,
                        "blocks": chunk_render_data["blocks"],
                        "bounds": chunk_render_data["bounds"]
                    })

                    # Merge sprites
                    if "sprites" in chunk_render_data:
                        all_sprites.update(chunk_render_data["sprites"])

                    # Update viewport bounds only for first chunk with blocks
                    if chunks_with_blocks == 0:
                        viewport_min_x = chunk_render_data["bounds"]["min_x"]
                        viewport_max_x = chunk_render_data["bounds"]["max_x"]
                        viewport_min_y = chunk_render_data["bounds"]["min_y"]
                        viewport_max_y = chunk_render_data["bounds"]["max_y"]
                    else:
                        viewport_min_x = min(viewport_min_x, chunk_render_data["bounds"]["min_x"])
                        viewport_max_x = max(viewport_max_x, chunk_render_data["bounds"]["max_x"])
                        viewport_min_y = min(viewport_min_y, chunk_render_data["bounds"]["min_y"])
                        viewport_max_y = max(viewport_max_y, chunk_render_data["bounds"]["max_y"])

                    chunks_with_blocks += 1
                    total_blocks += len(chunk_render_data["blocks"])

        print(f"[DEBUG] Found {chunks_with_blocks} chunks with blocks out of {(max_chunk_x - min_chunk_x + 1) * (max_chunk_z - min_chunk_z + 1)} total chunks")

        # Sort all chunks by distance from center for loading priority
        chunks_data.sort(key=lambda c: abs(c["chunk_x"] - center_x) + abs(c["chunk_z"] - center_z))

        processing_time = int((time.time() - start_time) * 1000)  # ms

        viewport_data = {
            "center_chunk": {"x": center_x, "z": center_z},
            "view_distance": view_distance,
            "chunks": chunks_data,
            "sprites": all_sprites,
            "viewport_bounds": {
                "min_x": viewport_min_x,
                "max_x": viewport_max_x,
                "min_y": viewport_min_y,
                "max_y": viewport_max_y
            },
            "stats": {
                "total_chunks": len(chunks_data),
                "total_blocks": total_blocks,
                "load_time_ms": processing_time,
                "avg_blocks_per_chunk": total_blocks // max(1, len(chunks_data))
            }
        }

        print(f"[DEBUG] Final viewport data: {len(chunks_data)} chunks, {total_blocks} blocks")
        print(f"[DEBUG] Viewport bounds: x=[{viewport_min_x},{viewport_max_x}], y=[{viewport_min_y},{viewport_max_y}]")

        return APIResponse(
            status="success",
            data=viewport_data,
            timestamp=datetime.now(UTC)
        )

    except WorldNotLoadedError:
        raise

    except Exception as e:
        print(f"[ERROR] Failed to get viewport render data: {e}")
        raise HTTPException(status_code=500, detail="Failed to get viewport render data") from e


@router.get(
    "/tile/{tile_x}/{tile_z}",
    response_model=APIResponse[TileDataResponse],
    summary="Get tile data",
    description="Returns data for a tile (square area of chunks). Optimized for progressive loading in the viewer.",
    status_code=200
)
async def get_tile(
    tile_x: int,
    tile_z: int,
    size: int = Query(
        default=16,
        ge=1,
        le=32,
        description="Tile size in chunks (default: 16, max: 32)"
    ),
    world_service: WorldService = Depends(get_world_service)
) -> APIResponse[TileDataResponse]:
    """
    Get data for a tile-based rendering system.

    A tile is a square area of chunks. For example, a 16x16 tile contains 256 chunks (256x256 blocks).
    This is perfect for progressive loading in the isometric viewer.

    **Parameters:**
    - tile_x, tile_z: Tile coordinates
    - size: Number of chunks per tile side (default: 16, max: 32)

    **Returns:**
    - tile_x, tile_z: Tile coordinates
    - tile_size: Size in chunks
    - start_chunk_x, start_chunk_z: Starting chunk coordinates
    - chunks: Array of chunk data (in surface mode)
    - chunk_count: Number of chunks in the tile

    **Example:**
    - Tile (0, 0) with size 16 contains chunks from (0,0) to (15,15)
    - Tile (1, 0) with size 16 contains chunks from (16,0) to (31,15)
    """
    try:
        if not world_service.is_loaded():
            raise WorldNotLoadedError()

        tile_data = world_service.get_tile_data(tile_x, tile_z, size)

        return APIResponse(
            status="success",
            data=tile_data,
            timestamp=datetime.now(UTC)
        )

    except WorldNotLoadedError:
        raise

    except Exception as e:
        LOGGER.exception("Failed to get tile data")
        raise HTTPException(
            status_code=500,
            detail="Failed to get tile data"
        ) from e


@router.get(
    "/{chunk_x}/{chunk_z}/{chunk_h}",
    response_model=APIResponse[ChunkDataResponse],
    summary="Get chunk data",
    description="Returns chunk data in various formats: heightmap (lightest), surface (for rendering), isometric (3D data), render (pre-calculated 2D display), simplified, or full.",
    status_code=200
)
async def get_chunk(
    chunk_x: int,
    chunk_z: int,
    chunk_h: int,
    mode: Literal["heightmap", "surface", "isometric", "render", "simplified", "full"] = Query(
        default="heightmap",
        description="Data format: heightmap (~1KB), surface (~10-50KB), isometric (~5-20KB), render (~2-10KB pre-calculated), simplified (~5KB), or full (~500KB-2MB)"
    ),
    world_service: WorldService = Depends(get_world_service)
) -> APIResponse[ChunkDataResponse]:
    """
    Get chunk data in the specified format.

    **Modes:**
    - **heightmap**: Only heightmap data (lightest, ~1KB) - ideal for minimap
    - **surface**: Surface blocks with biomes (~10-50KB) - ideal for 2D rendering
    - **isometric**: Surface blocks with depth info (~5-20KB) - optimized for 3D isometric view
    - **render**: Pre-calculated 2D display data (~2-10KB) - ready for immediate rendering
    - **simplified**: Palette only (~5KB) - for basic visualization
    - **full**: All chunk data (heaviest, ~500KB-2MB) - complete chunk information

    **Returns:**
    - chunk_x, chunk_z: Chunk coordinates
    - chunk_h: Height of precedent chunk
    - heightmap: 16x16 array of heights (heightmap mode)
    - surface_blocks: Surface block data with biomes (surface/isometric modes)
    - render_data: Pre-calculated screen positions and sprites (render mode)
    - sections, palette: Chunk sections and block palette (simplified/full modes)

    **Render mode specifics:**
    - Returns isometric screen coordinates (screen_x, screen_y)
    - Includes sprite keys for optimized texture lookup
    - Blocks sorted back-to-front for correct rendering
    - Bounds calculated for viewport culling
    - Ready for immediate display without client-side calculations

    **Performance:**
    - Uses async processing with thread pool for 'isometric' mode
    - Multiple concurrent requests are processed in parallel
    - No waiting for previous requests to complete
    """
    try:
        if not world_service.is_loaded():
            raise WorldNotLoadedError()

        # Use async version for isometric mode (most commonly used)
        # This allows multiple requests to run in parallel
        if mode == "isometric":
            chunk_data = await world_service.get_chunk_data_async(chunk_x, chunk_z, chunk_h, mode)
        else:
            chunk_data = world_service.get_chunk_data(chunk_x, chunk_z, chunk_h, mode)

        if chunk_data is None:
            raise HTTPException(
                status_code=404,
                detail=f"Chunk ({chunk_x}, {chunk_z}) not found"
            )

        return APIResponse(
            status="success",
            data=chunk_data,
            timestamp=datetime.now(UTC)
        )

    except WorldNotLoadedError as exc:
        raise HTTPException(
            status_code=503,
            detail="World not loaded. Please upload a world first."
        ) from exc

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        ) from e

    except Exception as e:
        LOGGER.exception("Failed to get chunk data")
        raise HTTPException(
            status_code=500,
            detail="Failed to get chunk data"
        ) from e


@router.get(
    "/area/heightmap",
    response_model=APIResponse[AreaHeightmapResponse],
    summary="Get area heightmap",
    description="Returns heightmap for a large area (multiple chunks). Perfect for rendering large portions of the world.",
    status_code=200
)
async def get_area_heightmap(
    x1: int = Query(..., description="Minimum X coordinate (block)"),
    z1: int = Query(..., description="Minimum Z coordinate (block)"),
    x2: int = Query(..., description="Maximum X coordinate (block)"),
    z2: int = Query(..., description="Maximum Z coordinate (block)"),
    world_service: WorldService = Depends(get_world_service)
) -> APIResponse[AreaHeightmapResponse]:
    """
    Get heightmap for an entire area spanning multiple chunks.

    **Parameters:**
    - x1, z1: Minimum block coordinates
    - x2, z2: Maximum block coordinates

    **Returns:**
    - x1, z1, x2, z2: Area bounds
    - width, height: Area dimensions in blocks
    - heightmap: 2D array of heights for the entire area

    **Note:** Large areas may take longer to process. Consider using tiles for very large regions.
    """
    if x2 < x1 or z2 < z1 or x2 - x1 >= MAX_AREA_SIDE or z2 - z1 >= MAX_AREA_SIDE:
        raise HTTPException(
            status_code=400,
            detail=f"The area must have x2 >= x1, z2 >= z1 and at most {MAX_AREA_SIDE} blocks per side"
        )

    try:
        if not world_service.is_loaded():
            raise WorldNotLoadedError()

        # Validate coordinates
        if x1 > x2 or z1 > z2:
            raise HTTPException(
                status_code=400,
                detail="Invalid coordinates: x1 must be <= x2 and z1 must be <= z2"
            )

        # Limit area size to prevent overload (max 512x512 blocks)
        width = abs(x2 - x1) + 1
        height = abs(z2 - z1) + 1
        if width * height > 512 * 512:
            raise HTTPException(
                status_code=400,
                detail=f"Area too large ({width}x{height}). Maximum is 512x512 blocks."
            )

        area_data = world_service.get_area_heightmap(x1, z1, x2, z2)

        return APIResponse(
            status="success",
            data=area_data,
            timestamp=datetime.now(UTC)
        )

    except WorldNotLoadedError:
        raise

    except HTTPException:
        raise

    except Exception as e:
        LOGGER.exception("Failed to get area heightmap")
        raise HTTPException(
            status_code=500,
            detail="Failed to get area heightmap"
        ) from e
