"""
Response models for API endpoints.
Standardized response format for all endpoints.
"""

from pydantic import BaseModel, Field
from typing import Any, Optional, List, TypeVar, Generic
from datetime import datetime

TResponse = TypeVar("TResponseData")

class APIResponse(BaseModel, Generic[TResponse]):
    """Standardized API response wrapper."""

    status: str = Field(..., description="Response status: 'success' or 'error'")
    data: Optional[TResponse] = Field(None, description="Response data")
    error: Optional[str] = Field(None, description="Error message if status is 'error'")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    


class WorldInfoResponse(BaseModel):
    """World information response data."""
    
    dimension: str = Field(..., description="Current dimension (overworld, nether, end)")
    world_folder: str = Field(..., description="Path to world folder")
    region_dir: str = Field(..., description="Path to region directory")
    bounds: Optional[List[int]] = Field(None, description="World bounds [min_x, min_y, min_z, max_x, max_y, max_z]")
    loaded_regions: int = Field(..., description="Number of loaded regions")
    region_list: List[List[int]] = Field(..., description="List of loaded region coordinates [[rx, rz], ...]")
    cache_stats: Optional[dict] = Field(None, description="Cache statistics")
    
    class Config:
        json_schema_extra = {
            "example": {
                "dimension": "overworld",
                "world_folder": "/path/to/world",
                "region_dir": "/path/to/world/region",
                "bounds": [-512, -64, -512, 512, 320, 512],
                "loaded_regions": 4,
                "region_list": [[0, 0], [0, 1], [1, 0], [1, 1]],
                "cache_stats": {
                    "chunk_cache_size": 100,
                    "region_cache_size": 10
                }
            }
        }


class ChunkDataResponse(BaseModel):
    """Chunk data response in various formats."""
    
    chunk_x: int = Field(..., description="Chunk X coordinate")
    chunk_z: int = Field(..., description="Chunk Z coordinate")
    heightmap: Optional[List[List[int]]|int] = Field(None, description="16x16 heightmap array")
    surface_blocks: Optional[List[dict]|List[List]] = Field(None, description="Surface blocks with biomes (surface mode) or isometric blocks with depth info (isometric mode)")
    render_data: Optional[dict] = Field(None, description="Pre-calculated render data for optimized 2D display (render mode)")
    sections: Optional[List[dict]] = Field(None, description="Chunk sections (simplified/full mode)")
    palette: Optional[List[str]] = Field(None, description="Block palette (simplified/full mode)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunk_x": 0,
                "chunk_z": 0,
                "heightmap": [[64, 65, 64], [65, 66, 65]],
                "surface_blocks": [
                    {"x": 0, "y": 64, "z": 0, "block": "minecraft:grass_block", "biome": "plains"}
                ]
            }
        }


class AreaHeightmapResponse(BaseModel):
    """Area heightmap response for large regions."""
    
    x1: int = Field(..., description="Minimum X coordinate")
    z1: int = Field(..., description="Minimum Z coordinate")
    x2: int = Field(..., description="Maximum X coordinate")
    z2: int = Field(..., description="Maximum Z coordinate")
    width: int = Field(..., description="Width in blocks")
    height: int = Field(..., description="Height in blocks")
    heightmap: List[List[int]] = Field(..., description="2D heightmap array")
    
    class Config:
        json_schema_extra = {
            "example": {
                "x1": 0,
                "z1": 0,
                "x2": 64,
                "z2": 64,
                "width": 65,
                "height": 65,
                "heightmap": [[64, 65], [65, 66]]
            }
        }


class TileDataResponse(BaseModel):
    """Tile data response for progressive loading."""
    
    tile_x: int = Field(..., description="Tile X coordinate")
    tile_z: int = Field(..., description="Tile Z coordinate")
    tile_size: int = Field(..., description="Tile size in chunks")
    start_chunk_x: int = Field(..., description="Starting chunk X coordinate")
    start_chunk_z: int = Field(..., description="Starting chunk Z coordinate")
    chunks: List[dict] = Field(..., description="List of chunk data in the tile")
    chunk_count: int = Field(..., description="Number of chunks in the tile")
    
    class Config:
        json_schema_extra = {
            "example": {
                "tile_x": 0,
                "tile_z": 0,
                "tile_size": 16,
                "start_chunk_x": 0,
                "start_chunk_z": 0,
                "chunks": [],
                "chunk_count": 256
            }
        }


class BlockDataResponse(BaseModel):
    """Block data response at specific coordinates."""
    
    block_x: int = Field(..., description="Block X coordinate")
    block_y: int = Field(..., description="Block Y coordinate")
    block_z: int = Field(..., description="Block Z coordinate")
    id: str = Field(..., description="Type of the block")
    properties: Optional[dict] = Field(None, description="Additional properties about the block")
    
    class Config:
        json_schema_extra = {
            "example": {
                "block_x": 0,
                "block_y": 0,
                "block_z": 0,
                "id": "deepslate",
                "properties": {
                    "axis": "y"
                }
            }
        }


class BiomeDataResponse(BaseModel):
    """Biome data response at specific coordinates."""
    
    biome_x: int = Field(..., description="Biome X coordinate")
    biome_y: int = Field(..., description="Biome Y coordinate")
    biome_z: int = Field(..., description="Biome Z coordinate")
    id: str = Field(..., description="Biome at the specified coordinates")
    
    class Config:
        json_schema_extra = {
            "example": {
                "biome_x": 0,
                "biome_y": 0,
                "biome_z": 0,
                "id": "plains"
            }
        }

class BlockJsonDataResponse(BaseModel):
    """ Json's block data response for isometric's request. """

    block_name: str = Field(..., description="Block's name")
    resources: dict = Field(..., description="resources for isometric's requests") 
    type: str = Field(..., description="variant's type or multipart's type") 

    class Config:
        json_schema_extra = {
            "example": {
                "block_name": "diamond_block",
                "resources": {
                    "top": "diamond_block_top.webp",
                    "left": "diamond_block_left.webp"
                },
                "type": "variants"
            }
        }