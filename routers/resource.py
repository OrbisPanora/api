"""
Resource endpoints for the API.
Provides resources for each minecraft block.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from datetime import datetime
import os
import json
from models.responses import APIResponse, BlockJsonDataResponse
from utils.errors import InvalidBlockProperties
import logging
from services.resource_service import get_json_block

LOGGER = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/resources",
    tags=["resources"],
    responses={
        503: {"description": "World not loaded"},
        500: {"description": "Internal server error"}
    }
)

@router.get(
    "/images/{image}",
    summary="retrieve image isométrique",
    description="Return isometric image",
    status_code=200
)
async def get_image(
    image: str
):
    filepath = f"resources/images/{image}"

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(
        path=filepath,
        media_type="image/webp",
        filename=image
    )


@router.get(
    "/json",
    response_model=APIResponse[BlockJsonDataResponse],
    summary="retrieve json of a block",
    description="Return block's json",
    status_code=200
)
async def get_json(
    id: str,
    namespace: str = Query(default="minecraft"),
    properties: str = Query(default={}),
    biome: str = Query(default="biome")
) -> APIResponse[BlockJsonDataResponse]:
    try:
        json_data = get_json_block(id=id, namespace=namespace, properties=properties, biome=biome)

        if json_data is None:
            raise HTTPException(
                status_code=404,
                detail=f"Json's {id} not found"
            )
        
        return APIResponse(
            status="success",
            data=json_data,
            timestamp=datetime.utcnow()
        )
    except InvalidBlockProperties:
        raise HTTPException(
            status_code=400
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail = f"Block {id},  unknown or not found"
        )
