"""
Chunk endpoints for the API.
Provides chunk data in various formats for the isometric viewer.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..models.responses import (
    APIResponse,
    AreaHeightmapResponse,
    ChunkDataResponse,
    IsometricChunkResponse,
    TileDataResponse,
)
from ..services.world_service import WorldService, get_world_service
from ..utils.errors import WorldNotLoadedError
from ..utils.timing import server_timing

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
    response_model=APIResponse[IsometricChunkResponse | ChunkDataResponse],
    summary="Get chunk data",
    description="Returns chunk data in various formats: heightmap (lightest), surface (blocks with biomes), isometric (the blocks the viewer draws), simplified, or full.",
    status_code=200
)
async def get_chunk(
    chunk_x: int,
    chunk_z: int,
    chunk_h: int,
    response: Response,
    mode: Literal["heightmap", "surface", "isometric", "simplified", "full"] = Query(
        default="heightmap",
        description="Data format: heightmap (~1KB), surface (~10-50KB), isometric (~2-20KB), simplified (~5KB), or full (~500KB-2MB)"
    ),
    world_service: WorldService = Depends(get_world_service)
) -> APIResponse[IsometricChunkResponse | ChunkDataResponse]:
    """
    Get chunk data in the specified format.

    **Modes:**
    - **heightmap**: Only heightmap data (lightest, ~1KB) - ideal for minimap
    - **surface**: Surface blocks with biomes (~10-50KB) - ideal for 2D rendering
    - **isometric**: The blocks that can be seen, as positions and a palette (see IsometricChunkResponse) - the viewer projects them
    - **simplified**: Palette only (~5KB) - for basic visualization
    - **full**: All chunk data (heaviest, ~500KB-2MB) - complete chunk information

    **Returns:**
    - chunk_x, chunk_z: Chunk coordinates
    - chunk_h: Height of precedent chunk
    - heightmap: 16x16 array of heights (heightmap mode)
    - surface_blocks: Surface block data with biomes (surface mode)
    - isometric mode: surface_y, palette and the lists x, y, z, block (see IsometricChunkResponse)
    - sections, palette: Chunk sections and block palette (simplified/full modes)

    **Performance:**
    - Uses the worker processes for 'isometric' mode
    - Multiple concurrent requests are processed in parallel
    - No waiting for previous requests to complete
    """
    try:
        if not world_service.is_loaded():
            raise WorldNotLoadedError()

        # Use async version for isometric mode (most commonly used)
        # This allows multiple requests to run in parallel
        if mode == "isometric":
            started = time.perf_counter()
            chunk_data, timings = await world_service.get_isometric_chunk_timed(chunk_x, chunk_z)
            timings["total"] = (time.perf_counter() - started) * 1000
            cold = bool(timings.pop("cold", 0.0))
            blocks = int(timings.pop("blocks", 0.0))
            response.headers["Server-Timing"] = server_timing(timings, cold=int(cold), blocks=blocks)
            LOGGER.debug("isometric chunk (%s, %s) %s", chunk_x, chunk_z, response.headers["Server-Timing"])
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
