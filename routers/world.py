"""
World endpoints for the API.
Provides information about the Minecraft world.
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from models.responses import APIResponse, WorldInfoResponse
from services.world_service import WorldService, get_world_service
from utils.errors import WorldNotLoadedError


router = APIRouter(
    prefix="/api/worlds",
    tags=["worlds"],
    responses={
        503: {"description": "World not loaded"},
        500: {"description": "Internal server error"}
    }
)


@router.get(
    "/current",
    response_model=APIResponse[WorldInfoResponse],
    summary="Get current world information",
    description="Returns metadata about the currently loaded Minecraft world including dimension, bounds, and loaded regions.",
    status_code=200
)
async def get_current_world(
    world_service: WorldService = Depends(get_world_service)
) -> APIResponse[WorldInfoResponse]:
    """
    Get comprehensive world information.
    
    Returns:
    - dimension: Current dimension (overworld, nether, end)
    - bounds: World boundaries
    - loaded_regions: Number of loaded regions
    - region_list: List of loaded region coordinates
    - cache_stats: Cache statistics
    """
    try:
        if not world_service.is_loaded():
            raise WorldNotLoadedError()
        
        world_info = world_service.get_world_info()
        
        return APIResponse(
            status="success",
            data=world_info,
            timestamp=datetime.utcnow()
        )
    
    except WorldNotLoadedError:
        raise
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get world info: {str(e)}"
        )


@router.get(
    "/health",
    summary="Health check",
    description="Check if the world is loaded and API is operational."
)
async def health_check(
    world_service: WorldService = Depends(get_world_service)
) -> dict:
    """
    Simple health check endpoint.
    
    Returns:
    - status: "healthy" if world is loaded
    - world_loaded: boolean
    """
    is_loaded = world_service.is_loaded()
    
    return {
        "status": "healthy" if is_loaded else "unhealthy",
        "world_loaded": is_loaded,
        "timestamp": datetime.utcnow().isoformat()
    }
