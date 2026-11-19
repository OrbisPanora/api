"""
Resource endpoints for the API.
Provides resources for each minecraft block.
"""
import logging
import os
from datetime import UTC, datetime
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, RootModel

from ..models.responses import APIResponse, BlockJsonDataResponse
from ..services.resource_service import get_json_block
from ..settings import get_settings
from ..utils.errors import InvalidBlockProperties

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
    filepath = f"{get_settings().resources_dir}/images/{image}"

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
            timestamp=datetime.now(UTC)
        )
    except InvalidBlockProperties as exc:
        raise HTTPException(
            status_code=400
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail = f"Block {id},  unknown or not found"
        ) from exc

class BlockItem(BaseModel):
    biome: str
    properties: Dict[str, str] = Field(default_factory=dict)
    side: int
    coordinates: Optional[List[List[Union[int, float]]]] = None
    namespace: str = "minecraft"

# This represents the dictionary where keys are block names
class BlockMap(RootModel):
    root: Dict[str, List[BlockItem]]

class PaletteRequest(BaseModel):
    blocks: List[BlockMap]  # List containing one BlockMap

@router.post("/palette")
def get_palette(request: PaletteRequest) -> APIResponse:
    palette = {}

    # Access the root dictionary from the first BlockMap in the list
    blocks_dict = request.blocks[0].root

    for block_name, block_variants in blocks_dict.items():
        # Initialize list for this block if not exists
        if block_name not in palette:
            palette[block_name] = []

        for variant in block_variants:
            try:
                json_data = get_json_block(
                    id=block_name,
                    namespace=variant.namespace,
                    properties=variant.properties,
                    biome=variant.biome
                )

                # Add this variant's data
                palette[block_name].append({
                    "biome": variant.biome,
                    "properties": variant.properties,
                    "resources": json_data.resources,
                    "type": json_data.type
                })

            except FileNotFoundError:
                LOGGER.warning(f"Block {block_name} not found")
                continue
            except InvalidBlockProperties as e:
                LOGGER.warning(f"Invalid properties for {block_name}: {e}")
                continue
            except Exception as e:
                LOGGER.error(f"Unexpected error for {block_name}: {e}")
                continue

    return APIResponse(
        status="success",
        data=palette,
        timestamp=datetime.now()
    )
