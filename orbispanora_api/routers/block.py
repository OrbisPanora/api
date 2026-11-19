"""
Block endpoints for the API.
Provides block data in various formats for the isometric viewer.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from ..models.responses import APIResponse, BlockDataResponse
from ..services.world_service import WorldService, get_world_service
from ..utils.errors import WorldNotLoadedError

LOGGER = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/blocks",
    tags=["blocks"],
    responses={
        404: {"description": "Block not found"},
        400: {"description": "Invalid parameters"},
        503: {"description": "World not loaded"},
        500: {"description": "Internal server error"}
    }
)

@router.get(
    "/{block_x}/{block_y}/{block_z}",
    response_model=APIResponse[BlockDataResponse],
    summary="Get block data",
    description="Returns block data at specified coordinates.",
    status_code=200
)
async def get_block(
    block_x: int,
    block_y: int,
    block_z: int,
    world_service: 'WorldService' = Depends(get_world_service)
) -> APIResponse[BlockDataResponse]:
    """
    Get block data at the specified coordinates.

    **Returns:**
    - block_x, block_y, block_z: Block coordinates
    - id: Type of the block
    - properties: Additional properties about the block
    """
    try:
        if not world_service.is_loaded():
            raise WorldNotLoadedError()

        block_data = world_service.get_block_data(block_x, block_y, block_z)

        if block_data is None:
            raise HTTPException(status_code=404, detail=f"Block not found at ({block_x}, {block_y}, {block_z})")

        return APIResponse(
            status="success",
            data=block_data,
            timestamp=datetime.now(UTC)
        )

    except WorldNotLoadedError:
        raise

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        ) from e

    except Exception as e:
        LOGGER.exception("Internal server error")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        ) from e
