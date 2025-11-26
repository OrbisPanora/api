"""
Resource endpoints for the API.
Provides resources for each minecraft block.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
import os
import json
from models.responses import APIResponse, WorldInfoResponse
from services.world_service import WorldService, get_world_service
from utils.errors import WorldNotLoadedError


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
        media_type="image/png",
        filename=name
    )


@router.get(
    "/json",
    summary="retrieve image isométrique",
    description="Return isometric image",
    status_code=200
)
async def get_json(
    id: str,
    namespace: str = Query(default="minecraft"),
    properties: str = Query(default={})
) -> dict:
    
    blockstates_path = f"resources/json/blockstates"
    blocks_path = f"resources/json/blocks"

    filename = id + '.json'

    block = os.path.join(blockstates_path, filename)

    if not os.path.exists(block):
        raise HTTPException(status_code=404, detail="json not found")
    
    with open(block, 'r') as f:
        block_data = json.load(f)
    
    if properties != {}:
        for state, props in block_data["variants"].items():
            attributes = dict(part.split("=") for part in state.split(","))

            if all(k in block.properties and str(block.properties[k]) == v for k, v in attributes.items()):
                model = props["model"]
                break

    else:
        model = block_data[""]
        
    model_name = model.split("/")[-1]
    json_file = model_name + '.json'
    texture = {}
    with open(os.path.join(block_models_path, json_file), 'r') as f:
        model_data = json.load(f)
    if len(model_data["textures"] == 1):
        if "all" in model_data["textures"].keys():
            texture.append({"top": model_data["textures"]["all"].split("/")[-1]+'.png'})
            texture.append({"left": model_data["textures"]["all"].split("/")[-1]+'.png'})
        else:
            texture.append({"top": model_data["textures"][0].split("/")[-1]+'.png'})
    else:
        if "side" in model_data["textures"].keys():
            texture.append({"top": model_data["textures"]["top"].split("/")[-1]+'.png'})
            texture.append({"left": model_data["textures"]["side"].split("/")[-1]+'.png'})
        else:
            texture.append({"top": model_data["textures"]["top"].split("/")[-1]+'.png'})
            texture.append({"left": model_data["textures"]["top"].split("/")[-1]+'.png'})

    return {
        "name": id,
        "textures": texture
    }
