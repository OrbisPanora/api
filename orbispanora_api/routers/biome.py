"""
Biom endpoints for the API.
Provides biom data in various formats for the isometric viewer.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from ..models.responses import APIResponse, BiomeDataResponse
from ..services.world_service import WorldService, get_world_service
from ..utils.errors import WorldNotLoadedError

router = APIRouter(
    prefix="/api/biomes",
    tags=["biomes"],
    responses={
        404: {"description": "Biome not found"},
        400: {"description": "Invalid parameters"},
        503: {"description": "World not loaded"},
        500: {"description": "Internal server error"}
    }
)

@router.get(
    "/{biome_x}/{biome_y}/{biome_z}",
    response_model=APIResponse[BiomeDataResponse],
    summary="Get biome data",
    description="Returns biome data at specified coordinates.",
    status_code=200
)
async def get_biome(
    biome_x: int,
    biome_y: int,
    biome_z: int,
    world_service: WorldService = Depends(get_world_service)
) -> APIResponse[BiomeDataResponse]:
    """
    Get biome data at the specified coordinates.

    **Returns:**
    - biome_x, biome_y, biome_z: Biome coordinates
    - id: Type of the biome
    - properties: Additional properties about the biome
    """
    try:
        if not world_service.is_loaded():
            raise WorldNotLoadedError()

        biome_data = world_service.get_biome_data(biome_x, biome_y, biome_z)

        if biome_data is None:
            raise HTTPException(status_code=404, detail=f"Biome not found at ({biome_x}, {biome_y}, {biome_z})")

        return APIResponse(
            status="success",
            data=biome_data,
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
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get biom data: {str(e)}"
        ) from e
