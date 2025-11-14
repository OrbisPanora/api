"""
Biom endpoints for the API.
Provides biom data in various formats for the isometric viewer.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from typing import Literal

from models.responses import APIResponse
from services.world_service import WorldService, get_world_service
from utils.errors import WorldNotLoadedError

router = APIRouter(
    prefix="/api/bioms",
    tags=["bioms"],
    responses={
        404: {"description": "Biom not found"},
        400: {"description": "Invalid parameters"},
        503: {"description": "World not loaded"},
        500: {"description": "Internal server error"}
    }
)

@router.get(
    "/{biom_x}/{biom_z}",
    response_model=APIResponse,
    summary="Get biom data",
    description="Returns biom data at specified coordinates.",
    status_code=200
)
async def get_biom(
    biom_x: int,
    biom_z: int,
    world_service: WorldService = Depends(get_world_service)
) -> APIResponse:
    """
    Get biom data at the specified coordinates.
    
    **Returns:**
    - biom_x, biom_z: Biom coordinates
    - id: Type of the biom
    - properties: Additional properties about the biom
    """
    try:
        if not world_service.is_loaded():
            raise WorldNotLoadedError()

        biom_data = world_service.get_biom_data(biom_x, biom_z)

        if biom_data is None:
            raise HTTPException(status_code=404, detail=f"Biom not found at ({biom_x}, {biom_z})")

        return APIResponse(
            status="success",
            data=biom_data,
            timestamp=datetime.utcnow()
        )
    
    except WorldNotLoadedError:
        raise

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get biom data: {str(e)}"
        )