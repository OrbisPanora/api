"""Routers package for API endpoints."""

from .world import router as world_router
from .chunk import router as chunk_router
from .block import router as block_router
from .biome import router as biome_router
from .upload import router as upload_router
from .isometric import router as isometric_router

__all__ = ["world_router", "chunk_router", "block_router", "biome_router", "upload_router", "isometric_router"]