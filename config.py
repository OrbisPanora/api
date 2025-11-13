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
    cors_origins: str = "http://localhost:4200,http://localhost:3000"
    
    # Logging
    log_level: str = "INFO"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()


def validate_settings():
    """Validate required settings."""
    if not settings.world_path:
        raise ValueError("WORLD_PATH environment variable is required")
    
    if not os.path.exists(settings.world_path):
        raise ValueError(f"World path does not exist: {settings.world_path}")
    
    print(f"Configuration loaded")
    print(f"  - World path: {settings.world_path}")
    print(f"  - Dimension: {settings.world_dimension}")
    print(f"  - API port: {settings.api_port}")
    print(f"  - CORS origins: {', '.join(settings.cors_origins)}")
