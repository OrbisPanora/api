"""
Response models for API endpoints.
Standardized response format for all endpoints.
"""

from pydantic import BaseModel, Field
from typing import Any, Optional, List
from datetime import datetime


class APIResponse(BaseModel):
    """Standardized API response wrapper."""
    
    status: str = Field(..., description="Response status: 'success' or 'error'")
    data: Optional[Any] = Field(None, description="Response data")
    error: Optional[str] = Field(None, description="Error message if status is 'error'")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {"key": "value"},
                "error": None,
                "timestamp": "2024-01-01T00:00:00"
            }
        }


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
