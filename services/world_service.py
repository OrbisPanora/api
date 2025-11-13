"""
World service for managing Minecraft world instance.
Singleton pattern to ensure only one World instance is loaded.
"""

from typing import Optional

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
        return self.world.get_world_info()
    
    def is_loaded(self) -> bool:
        """Check if world is loaded."""
        return self._world is not None
    
    def get_chunk_data(self, chunk_x: int, chunk_z: int, mode: str = 'heightmap') -> dict:
        """
        Get chunk data in various formats.
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_z: Chunk Z coordinate
            mode: Data format ('heightmap', 'surface', 'simplified', 'full')
        
        Returns:
            Chunk data dictionary or None if chunk not found
        """
        return self.world.get_chunk_data(chunk_x, chunk_z, mode)
    
    def get_area_heightmap(self, x1: int, z1: int, x2: int, z2: int) -> dict:
        """
        Get heightmap for an area.
        
        Args:
            x1, z1: Minimum block coordinates
            x2, z2: Maximum block coordinates
        
        Returns:
            Area heightmap dictionary
        """
        return self.world.get_area_heightmap(x1, z1, x2, z2)
    
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
        return self.world.get_tile_data(tile_x, tile_z, tile_size)

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
