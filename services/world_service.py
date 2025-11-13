"""
World service for managing Minecraft world instance.
Singleton pattern to ensure only one World instance is loaded.
"""

import sys
import os
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

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
