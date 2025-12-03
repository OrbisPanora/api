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
from pydantic import BaseModel
from typing import List, Dict

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
        print("TEST")
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

class BlockItem(BaseModel):
    id: str
    namespace: str
    biome: str
    properties: dict = {}

class PaletteRequest(BaseModel):
    blocks: Dict[str, BlockItem]

@router.post("/palette")
def get_palette(request: PaletteRequest) -> APIResponse:
    palette = {}

    for name, data in request.blocks.items():
        json_data = get_json_block(
            id=data.id,
            namespace=data.namespace,
            properties=data.properties,
            biome=data.biome
        )
        side = name.split("_")[-1]
        image = {}
        image[side] = json_data.textures[side]
        palette[name] = image

    return APIResponse(
        status="success",
        data=palette,
        timestamp=datetime.now()
    )
