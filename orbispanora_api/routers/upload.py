"""
Upload endpoints for the API.
Provides endpoints for uploading Minecraft world files.
Supports chunked upload for large files.

Limits (see `settings.py`): the size of the zip file, the size of one chunk, the number of
uploads in progress and how long an idle one is kept.
"""

import logging
import re
import shutil
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..models.responses import APIResponse, WorldInfoResponse
from ..services.world_service import WorldService, get_world_service
from ..settings import get_settings

LOGGER = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/upload",
    tags=["upload"],
    responses={
        400: {"description": "Invalid file or request"},
        413: {"description": "File too large"},
        429: {"description": "Too many uploads in progress"},
        500: {"description": "Internal server error"}
    }
)

VALID_DIMENSIONS = ("overworld", "nether", "end")
_UPLOAD_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_READ_BLOCK = 1024 * 1024

#: Recommended size of one chunk, in bytes.
RECOMMENDED_CHUNK_SIZE = 5 * 1024 * 1024

# Storage for ongoing chunked uploads. The sessions live in this process only.
chunked_uploads: Dict[str, dict] = {}


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


def _max_upload_bytes() -> int:
    return get_settings().upload_max_size_mb * 1024 * 1024


def _chunks_dir() -> Path:
    """The directory holding the chunks of uploads in progress, created if needed."""
    directory = get_settings().upload_chunks_dir
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


def _drop_session(upload_id: str) -> None:
    """Forget an upload and delete its files."""
    info = chunked_uploads.pop(upload_id, None)
    if info is not None:
        shutil.rmtree(info["upload_dir"], ignore_errors=True)


def _drop_expired_sessions() -> None:
    """Delete the uploads that received nothing for longer than the configured time."""
    limit = time.monotonic() - get_settings().upload_session_ttl
    for upload_id in [key for key, info in chunked_uploads.items() if info["last_activity"] < limit]:
        _drop_session(upload_id)


def _get_session(upload_id: str) -> dict:
    """The session of `upload_id`, or an HTTP 404."""
    _drop_expired_sessions()
    info = chunked_uploads.get(upload_id) if _UPLOAD_ID.fullmatch(upload_id) else None
    if info is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    info["last_activity"] = time.monotonic()
    return info


async def _save_limited(source: UploadFile, destination: Path, limit: int) -> int:
    """Write `source` to `destination` and return the size. Over `limit`: the file is deleted and HTTP 413 is raised."""
    size = 0
    try:
        with open(destination, "wb") as output:
            while block := await source.read(_READ_BLOCK):
                size += len(block)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"The upload is larger than the {limit} bytes allowed")
                output.write(block)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return size


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
    settings = get_settings()
    if not filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only .zip files are allowed")

    if dimension not in VALID_DIMENSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid dimension. Must be one of: {', '.join(VALID_DIMENSIONS)}")

    if not 0 < total_size <= _max_upload_bytes():
        raise HTTPException(status_code=413, detail=f"The size must be between 1 and {_max_upload_bytes()} bytes")

    max_chunk = settings.upload_max_chunk_mb * 1024 * 1024
    if not -(-total_size // max_chunk) <= total_chunks <= total_size:
        raise HTTPException(status_code=400, detail="The number of chunks does not fit the total size")

    _drop_expired_sessions()
    if len(chunked_uploads) >= settings.upload_max_sessions:
        raise HTTPException(status_code=429, detail="Too many uploads in progress. Try again later")

    upload_id = str(uuid.uuid4())
    upload_dir = _chunks_dir() / upload_id
    upload_dir.mkdir(mode=0o700)
    chunked_uploads[upload_id] = {
        "filename": filename,
        "total_chunks": total_chunks,
        "total_size": total_size,
        "dimension": dimension,
        "received_chunks": set(),
        "received_bytes": 0,
        "upload_dir": upload_dir,
        "created_at": datetime.now(UTC),
        "last_activity": time.monotonic(),
    }

    return APIResponse(
        status="success",
        data=ChunkUploadInit(
            upload_id=upload_id,
            chunk_size=RECOMMENDED_CHUNK_SIZE,
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
    upload_info = _get_session(upload_id)

    if chunk_index < 0 or chunk_index >= upload_info["total_chunks"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid chunk index. Must be between 0 and {upload_info['total_chunks'] - 1}"
        )

    if chunk_index in upload_info["received_chunks"]:
        raise HTTPException(status_code=400, detail=f"Chunk {chunk_index} already received")

    remaining = upload_info["total_size"] - upload_info["received_bytes"]
    limit = min(get_settings().upload_max_chunk_mb * 1024 * 1024, remaining)
    chunk_path = upload_info["upload_dir"] / f"chunk_{chunk_index:06d}"
    size = await _save_limited(chunk, chunk_path, limit)

    upload_info["received_chunks"].add(chunk_index)
    upload_info["received_bytes"] += size
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
    upload_info = _get_session(upload_id)

    if len(upload_info["received_chunks"]) != upload_info["total_chunks"]:
        missing = upload_info["total_chunks"] - len(upload_info["received_chunks"])
        raise HTTPException(status_code=400, detail=f"Upload incomplete. Missing {missing} chunks.")

    if upload_info["received_bytes"] != upload_info["total_size"]:
        _drop_session(upload_id)
        raise HTTPException(status_code=400, detail="The chunks do not add up to the declared size")

    final_zip_path = upload_info["upload_dir"] / "world.zip"
    try:
        with open(final_zip_path, "wb") as final_file:
            for i in range(upload_info["total_chunks"]):
                with open(upload_info["upload_dir"] / f"chunk_{i:06d}", "rb") as chunk_file:
                    shutil.copyfileobj(chunk_file, final_file)

        world_service.load_world_from_zip(str(final_zip_path), upload_info["dimension"])
        world_info = world_service.get_world_info()

        return APIResponse(
            status="success",
            data=world_info,
            timestamp=datetime.now(UTC)
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    except Exception as e:
        LOGGER.exception("Failed to finalize upload")
        raise HTTPException(status_code=500, detail="Failed to finalize upload") from e

    finally:
        _drop_session(upload_id)


@router.delete(
    "/cancel/{upload_id}",
    summary="Cancel a chunked upload",
    description="Cancel an ongoing chunked upload and cleanup temporary files."
)
async def cancel_chunked_upload(upload_id: str):
    """Cancel an ongoing chunked upload and cleanup."""
    _get_session(upload_id)
    _drop_session(upload_id)
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

    **File requirements:**
    - Must be a valid zip file with a Minecraft world (level.dat file)
    - Maximum size: `ORBISPANORA_UPLOAD_MAX_SIZE_MB` (500 MB by default)
    - Supported extensions: .zip

    **Returns:** the information of the loaded world (dimension, bounds, regions).
    """
    if not (file.filename or '').lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only .zip files are allowed")

    if dimension not in VALID_DIMENSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid dimension. Must be one of: {', '.join(VALID_DIMENSIONS)}")

    with tempfile.TemporaryDirectory(dir=_chunks_dir()) as staging:
        zip_path = Path(staging) / "world.zip"
        await _save_limited(file, zip_path, _max_upload_bytes())
        try:
            world_service.load_world_from_zip(str(zip_path), dimension)
            return APIResponse(
                status="success",
                data=world_service.get_world_info(),
                timestamp=datetime.now(UTC)
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            LOGGER.exception("Failed to upload and load world")
            raise HTTPException(status_code=500, detail="Failed to upload and load world") from e
