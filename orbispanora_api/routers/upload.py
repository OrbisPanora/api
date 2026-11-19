"""
Upload endpoints for the API.
Provides endpoints for uploading Minecraft world files.
Supports chunked upload for large files.
"""

import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from typing import Dict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..models.responses import APIResponse, WorldInfoResponse
from ..services.world_service import WorldService, get_world_service

router = APIRouter(
    prefix="/api/upload",
    tags=["upload"],
    responses={
        400: {"description": "Invalid file or request"},
        413: {"description": "File too large"},
        500: {"description": "Internal server error"}
    }
)

# Storage for ongoing chunked uploads
# In production, consider using Redis or a database
chunked_uploads: Dict[str, dict] = {}

# Directory for storing chunks temporarily
CHUNKS_DIR = os.path.join(tempfile.gettempdir(), "minecraft_chunks")
os.makedirs(CHUNKS_DIR, exist_ok=True)


class ChunkUploadInit(BaseModel):
    """Response model for chunk upload initialization"""
    upload_id: str
    chunk_size: int
    message: str


class ChunkUploadStatus(BaseModel):
    """Response model for chunk upload status"""
    upload_id: str
    chunks_received: int
    total_chunks: int
    is_complete: bool


@router.post(
    "/init",
    response_model=APIResponse[ChunkUploadInit],
    summary="Initialize a chunked upload",
    description="Start a new chunked upload session for large files."
)
async def init_chunked_upload(
    filename: str = Form(..., description="Original filename"),
    total_chunks: int = Form(..., description="Total number of chunks"),
    total_size: int = Form(..., description="Total file size in bytes"),
    dimension: str = Form(default="overworld", description="Dimension to load")
) -> APIResponse[ChunkUploadInit]:
    """
    Initialize a chunked upload session.

    Returns an upload_id that must be used for subsequent chunk uploads.
    """
    # Validate file extension
    if not filename.lower().endswith('.zip'):
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

    # Generate unique upload ID
    upload_id = str(uuid.uuid4())

    # Create directory for this upload's chunks
    upload_dir = os.path.join(CHUNKS_DIR, upload_id)
    os.makedirs(upload_dir, exist_ok=True)

    # Store upload metadata
    chunked_uploads[upload_id] = {
        "filename": filename,
        "total_chunks": total_chunks,
        "total_size": total_size,
        "dimension": dimension,
        "received_chunks": set(),
        "upload_dir": upload_dir,
        "created_at": datetime.now(UTC)
    }

    # Recommended chunk size (5MB)
    chunk_size = 5 * 1024 * 1024

    return APIResponse(
        status="success",
        data=ChunkUploadInit(
            upload_id=upload_id,
            chunk_size=chunk_size,
            message=f"Upload initialized. Send {total_chunks} chunks."
        ),
        timestamp=datetime.now(UTC)
    )


@router.post(
    "/chunk",
    response_model=APIResponse[ChunkUploadStatus],
    summary="Upload a single chunk",
    description="Upload one chunk of the file. Chunks can be uploaded in any order."
)
async def upload_chunk(
    upload_id: str = Form(..., description="Upload session ID"),
    chunk_index: int = Form(..., description="Index of this chunk (0-based)"),
    chunk: UploadFile = File(..., description="The chunk data")
) -> APIResponse[ChunkUploadStatus]:
    """
    Upload a single chunk of the file.

    Chunks can be uploaded in any order. The server will reassemble them
    based on chunk_index.
    """
    # Validate upload session exists
    if upload_id not in chunked_uploads:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found. Please initialize upload first."
        )

    upload_info = chunked_uploads[upload_id]

    # Validate chunk index
    if chunk_index < 0 or chunk_index >= upload_info["total_chunks"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid chunk index. Must be between 0 and {upload_info['total_chunks'] - 1}"
        )

    # Check if chunk already received
    if chunk_index in upload_info["received_chunks"]:
        raise HTTPException(
            status_code=400,
            detail=f"Chunk {chunk_index} already received"
        )

    # Save chunk to disk
    chunk_path = os.path.join(upload_info["upload_dir"], f"chunk_{chunk_index:06d}")
    content = await chunk.read()

    with open(chunk_path, "wb") as f:
        f.write(content)

    # Mark chunk as received
    upload_info["received_chunks"].add(chunk_index)

    is_complete = len(upload_info["received_chunks"]) == upload_info["total_chunks"]

    return APIResponse(
        status="success",
        data=ChunkUploadStatus(
            upload_id=upload_id,
            chunks_received=len(upload_info["received_chunks"]),
            total_chunks=upload_info["total_chunks"],
            is_complete=is_complete
        ),
        timestamp=datetime.now(UTC)
    )


@router.post(
    "/finalize",
    response_model=APIResponse[WorldInfoResponse],
    summary="Finalize chunked upload and load world",
    description="Reassemble all chunks and load the Minecraft world."
)
async def finalize_chunked_upload(
    upload_id: str = Form(..., description="Upload session ID"),
    world_service: WorldService = Depends(get_world_service)
) -> APIResponse[WorldInfoResponse]:
    """
    Finalize the chunked upload by reassembling all chunks and loading the world.

    All chunks must be uploaded before calling this endpoint.
    """
    # Validate upload session exists
    if upload_id not in chunked_uploads:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found"
        )

    upload_info = chunked_uploads[upload_id]

    # Check if all chunks received
    if len(upload_info["received_chunks"]) != upload_info["total_chunks"]:
        missing = upload_info["total_chunks"] - len(upload_info["received_chunks"])
        raise HTTPException(
            status_code=400,
            detail=f"Upload incomplete. Missing {missing} chunks."
        )

    try:
        # Reassemble chunks into final file
        final_zip_path = os.path.join(CHUNKS_DIR, f"{upload_id}.zip")

        with open(final_zip_path, "wb") as final_file:
            for i in range(upload_info["total_chunks"]):
                chunk_path = os.path.join(upload_info["upload_dir"], f"chunk_{i:06d}")
                with open(chunk_path, "rb") as chunk_file:
                    final_file.write(chunk_file.read())

        print(f"Reassembled {upload_info['total_chunks']} chunks into {final_zip_path}")

        # Load the world
        world_service.load_world_from_zip(final_zip_path, upload_info["dimension"])
        world_info = world_service.get_world_info()

        return APIResponse(
            status="success",
            data=world_info,
            timestamp=datetime.now(UTC)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to finalize upload: {str(e)}"
        ) from e

    finally:
        # Cleanup: remove chunks directory and final zip
        try:
            shutil.rmtree(upload_info["upload_dir"], ignore_errors=True)
            if os.path.exists(final_zip_path):
                os.unlink(final_zip_path)
            del chunked_uploads[upload_id]
        except Exception:
            pass  # Ignore cleanup errors


@router.delete(
    "/cancel/{upload_id}",
    summary="Cancel a chunked upload",
    description="Cancel an ongoing chunked upload and cleanup temporary files."
)
async def cancel_chunked_upload(upload_id: str):
    """Cancel an ongoing chunked upload and cleanup."""
    if upload_id not in chunked_uploads:
        raise HTTPException(
            status_code=404,
            detail="Upload session not found"
        )

    upload_info = chunked_uploads[upload_id]

    # Cleanup
    try:
        shutil.rmtree(upload_info["upload_dir"], ignore_errors=True)
        del chunked_uploads[upload_id]
    except Exception:
        pass

    return APIResponse(
        status="success",
        data={"message": "Upload cancelled"},
        timestamp=datetime.now(UTC)
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
        if not (file.filename or '').lower().endswith('.zip'):
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
                timestamp=datetime.now(UTC)
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
        ) from e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload and load world: {str(e)}"
        ) from e
