"""
Configuration module for OrbisPanora API.
Handles environment variables and application settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Minecraft World Configuration
    world_path: str = ""
    world_dimension: str = "overworld"
    
    # API Configuration
    api_host: str = "localhost"
    api_port: int = 8000
    api_reload: bool = True
    api_title: str = "OrbisPanora API"
    api_description: str = "FastAPI backend for OrbisPanora isometric Minecraft world viewer"
    api_version: str = "1.0.0"
    
    # CORS Configuration
    cors_origins: str = "http://localhost:4200,http://localhost:3000,http://localhost:52568"
    
    # Logging
    log_level: str = "INFO"
    
    # Cache Configuration
    cache_enabled: bool = True
    cache_type: str = "memory"  # "memory" or "redis"
    redis_url: str = "redis://localhost:6379"
    cache_ttl_heightmap: int = 300  
    cache_ttl_surface: int = 120   
    cache_ttl_chunk: int = 600   
    
    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100 
    rate_limit_window: int = 60    
    
    # Upload Configuration
    upload_max_size_mb: int = 100  # Maximum upload size in MB
    upload_allowed_extensions: str = ".zip"  # Allowed file extensions
    temp_world_dir: str = "./temp_worlds"  # Directory for extracted worlds
    
    # File handling
    cleanup_temp_files: bool = True  # Clean up temp files after loading
    max_temp_worlds: int = 5  # Maximum number of temp worlds to keep  
    
    # Compression
    compression_enabled: bool = True
    compression_min_size: int = 500  
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()


def validate_settings():
    """Validate required settings."""
    # world_path is now optional - worlds will be loaded from uploads
    if settings.world_path and not os.path.exists(settings.world_path):
        raise ValueError(f"World path does not exist: {settings.world_path}")
    
    print(f"Configuration loaded")
    print(f"  - World path: {settings.world_path}")
    print(f"  - Dimension: {settings.world_dimension}")
    print(f"  - API port: {settings.api_port}")
    print(f"  - CORS origins: {settings.cors_origins}")
