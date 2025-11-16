"""
Upload endpoints for the API.
Provides endpoints for uploading Minecraft world files.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from datetime import datetime
import os
import tempfile

from models.responses import APIResponse, WorldInfoResponse
from services.world_service import WorldService, get_world_service
from config import settings

router = APIRouter(
    prefix="/api/upload",
    tags=["upload"],
    responses={
        400: {"description": "Invalid file or request"},
        413: {"description": "File too large"},
        500: {"description": "Internal server error"}
    }
)


@router.post(
    "/world",
    response_model=APIResponse[WorldInfoResponse],
    summary="Upload and load a Minecraft world",
    description="Upload a zip file containing a Minecraft world save. The API will extract the world and load it for use with other endpoints.",
    status_code=200
)
async def upload_world(
    file: UploadFile = File(..., description="Zip file containing the Minecraft world"),
    dimension: str = "overworld",
    world_service: WorldService = Depends(get_world_service)
) -> APIResponse[WorldInfoResponse]:
    """
    Upload and load a Minecraft world from a zip file.

    **Parameters:**
    - **file**: Zip file containing a Minecraft world (level.dat and region folder required)
    - **dimension**: Dimension to load (overworld, nether, end). Defaults to overworld.

    **Supported dimensions:**
    - overworld: Main world with surface and caves
    - nether: Nether dimension
    - end: End dimension

    **File requirements:**
    - Must be a valid zip file
    - Must contain a Minecraft world (level.dat file)
    - Maximum size: 100MB (configurable)
    - Supported extensions: .zip

    **Returns:**
    - World information including bounds, loaded regions, and cache stats
    - The uploaded world becomes the active world for all other API endpoints

    **Example response:**
    ```json
    {
        "status": "success",
        "data": {
            "dimension": "overworld",
            "world_folder": "/temp/world_123",
            "region_dir": "/temp/world_123/region",
            "bounds": [-512, -64, -512, 512, 320, 512],
            "loaded_regions": 4,
            "region_list": [[0, 0], [0, 1], [1, 0], [1, 1]]
        },
        "timestamp": "2023-12-01T12:00:00Z"
    }
    ```
    """
    try:
        # Validate file extension
        if not file.filename.lower().endswith('.zip'):
            raise HTTPException(
                status_code=400,
                detail="Only .zip files are allowed"
            )

        # Validate dimension
        valid_dimensions = ["overworld", "nether", "end"]
        if dimension not in valid_dimensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid dimension. Must be one of: {', '.join(valid_dimensions)}"
            )

        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
            temp_zip_path = temp_file.name
            content = await file.read()
            temp_file.write(content)

        try:
            # Load the world from the zip file
            print(f"Uploading world from {file.filename} ({len(content)} bytes)")
            world_service.load_world_from_zip(temp_zip_path, dimension)

            # Get world info to return
            world_info = world_service.get_world_info()

            return APIResponse(
                status="success",
                data=world_info,
                timestamp=datetime.utcnow()
            )

        finally:
            # Clean up the temporary zip file
            try:
                os.unlink(temp_zip_path)
            except Exception:
                pass  # Ignore cleanup errors

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
            detail=f"Failed to upload and load world: {str(e)}"
        )
