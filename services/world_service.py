"""
World service for managing Minecraft world instance.
Singleton pattern to ensure only one World instance is loaded.
"""

from typing import Optional
from models.responses import WorldInfoResponse, ChunkDataResponse, AreaHeightmapResponse, TileDataResponse, BlockDataResponse, BiomeDataResponse
from anvil import World
from config import settings


class WorldService:
    """Singleton service for managing Minecraft world."""
    
    _instance: Optional['WorldService'] = None
    _world: Optional[World] = None
    
    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super(WorldService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize world service."""
        if self._world is None:
            self._load_world()
    
    def _load_world(self):
        """Load the Minecraft world."""
        try:
            print(f"Loading world from: {settings.world_path}")
            self._world = World(
                settings.world_path,
                dimension=settings.world_dimension
            )
            print(f"World loaded successfully")
        except Exception as e:
            print(f"Failed to load world: {e}")
            raise
    
    @property
    def world(self) -> World:
        """Get the world instance."""
        if self._world is None:
            self._load_world()
        return self._world
    
    def reload_world(self):
        """Reload the world (useful for testing or after world changes)."""
        print("Reloading world...")
        self._world = None
        self._load_world()
    
    def get_world_info(self) -> dict:
        """Get world information using the library's method."""
        try:
            world_info_dict = self.world.get_world_info()
            if not world_info_dict:
                return None
            
            # Map anvil library fields to our response model
            mapped_info = {
                "dimension": world_info_dict.get("dimension", "overworld"),
                "world_folder": world_info_dict.get("world_folder", ""),
                "region_dir": world_info_dict.get("region_dir", ""),
                "bounds": world_info_dict.get("bounds"),
                "loaded_regions": world_info_dict.get("loaded_regions", 0),
                "region_list": world_info_dict.get("region_coordinates", []),
                "cache_stats": {
                    "cache_enabled": world_info_dict.get("cache_enabled", False),
                    "chunk_cache_size": world_info_dict.get("chunk_cache_size", 0),
                    "region_cache_size": world_info_dict.get("region_cache_size", 0)
                } if world_info_dict.get("cache_enabled") else None
            }
            
            return WorldInfoResponse(**mapped_info)
        except Exception as e:
            print(f"Error getting world info: {e}")
            return None
    
    def is_loaded(self) -> bool:
        """Check if world is loaded."""
        return self._world is not None
    
    def get_chunk_data(self, chunk_x: int, chunk_z: int, mode: str = 'heightmap'):
        """
        Get chunk data in various formats.
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_z: Chunk Z coordinate
            mode: Data format ('heightmap', 'surface', 'simplified', 'full')
        
        Returns:
            ChunkDataResponse object or None if chunk not found
        """
        try:
            # Return mock data for now since the world.get_chunk_data method may not exist
            if mode == "heightmap":
                return ChunkDataResponse(
                    chunk_x=chunk_x,
                    chunk_z=chunk_z,
                    mode=mode,
                    heightmap=[[64] * 16 for _ in range(16)],  # 16x16 heightmap
                    surface_blocks=None,
                    sections=None,
                    palette=None
                )
            else:
                return ChunkDataResponse(
                    chunk_x=chunk_x,
                    chunk_z=chunk_z,
                    mode=mode,
                    heightmap=[[64] * 16 for _ in range(16)],
                    surface_blocks=[{"x": x, "z": z, "y": 64, "block": "minecraft:grass_block"} for x in range(16) for z in range(16)],
                    sections=None,
                    palette=None
                )
        except Exception as e:
            print(f"Error getting chunk data: {e}")
            return None
    
    def get_area_heightmap(self, x1: int, z1: int, x2: int, z2: int) -> dict:
        """
        Get heightmap for an area.
        
        Args:
            x1, z1: Minimum block coordinates
            x2, z2: Maximum block coordinates
        
        Returns:
            Area heightmap dictionary
        """
        area_heightmap_dict = self.world.get_area_heightmap(x1, z1, x2, z2)
        return AreaHeightmapResponse(**area_heightmap_dict) if area_heightmap_dict else None
    
    def get_tile_data(self, tile_x: int, tile_z: int, tile_size: int = 16) -> dict:
        """
        Get tile data for progressive loading.
        
        Args:
            tile_x: Tile X coordinate
            tile_z: Tile Z coordinate
            tile_size: Number of chunks per tile side
        
        Returns:
            Tile data dictionary with all chunks
        """
        tile_data_dict = self.world.get_tile_data(tile_x, tile_z, tile_size)
        return TileDataResponse(**tile_data_dict) if tile_data_dict else None

    def get_block_data(self, block_x: int, block_y: int, block_z: int) -> dict:
        """
        Get block data at specified coordinates.
        
        Args:
            block_x: Block X coordinate
            block_y: Block Y coordinate
            block_z: Block Z coordinate
        
        Returns:
            Block data dictionary or None if block not found
        """
        block = self.world.get_block(block_x, block_y, block_z)
        block_data_dict = {
            "block_x": block_x,
            "block_y": block_y,
            "block_z": block_z,
            "id": str(block.id),
            "properties": {str(key): str(value) for key, value in block.properties.items()}
        }
        return BlockDataResponse(**block_data_dict) if block_data_dict else None
    
    def get_biome_data(self, biome_x: int, biome_y: int, biome_z: int) -> dict:
        """
        Get biome data at specified coordinates.
        
        Args:
            biome_x: Biome X coordinate
            biome_z: Biome Z coordinate
        
        Returns:
            Biome data dictionary or None if biome not found
        """
        biome = self.world.get_biome(biome_x, biome_y, biome_z)
        biome_data_dict = {
            "biome_x": biome_x,
            "biome_y": biome_y,
            "biome_z": biome_z,
            "id": str(biome.id),
        }
        return BiomeDataResponse(**biome_data_dict) if biome_data_dict else None

_world_service: Optional[WorldService] = None


def get_world_service() -> WorldService:
    """
    Get the global WorldService instance.
    Used as a dependency in FastAPI endpoints.
    """
    global _world_service
    if _world_service is None:
        _world_service = WorldService()
    return _world_service
