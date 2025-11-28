"""
OrbisPanora API - FastAPI backend for isometric Minecraft world viewer.
Main application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from config import settings, validate_settings
from routers import world_router, chunk_router, block_router, biome_router, upload_router, resource_router, isometric_router
from services import get_world_service
from services.cache_service import init_cache_service, get_cache_service
from middleware import RateLimitMiddleware, GZipMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup
    print("\n" + "="*60)
    print("Starting OrbisPanora API")
    print("="*60)
    
    try:
        validate_settings()
        
        # Initialize cache service
        if settings.cache_enabled:
            ttl_config = {
                "heightmap": settings.cache_ttl_heightmap,
                "surface": settings.cache_ttl_surface,
                "chunk": settings.cache_ttl_chunk
            }
            cache_service = init_cache_service(
                settings.cache_type,
                settings.redis_url,
                ttl_config
            )
            print(f"Cache service initialized ({settings.cache_type})")
            print(f"  - Heightmap TTL: {settings.cache_ttl_heightmap}s")
            print(f"  - Surface TTL: {settings.cache_ttl_surface}s")
            print(f"  - Chunk TTL: {settings.cache_ttl_chunk}s")
        else:
            print("Cache disabled")
        
        world_service = get_world_service()
        print(f"World service initialized")
    except Exception as e:
        print(f"Failed to initialize: {e}")
        raise
    
    print("="*60)
    print(f"API ready at http://{settings.api_host}:{settings.api_port}")
    print(f"Docs available at http://{settings.api_host}:{settings.api_port}/docs")
    print("="*60 + "\n")
    
    yield
    
    # Shutdown
    print("\n" + "="*60)
    print("Shutting down OrbisPanora API")
    print("="*60 + "\n")


# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)


# Configure middlewares
# 1. Compression (first, to compress all responses)
if settings.compression_enabled:
    app.add_middleware(
        GZipMiddleware,
        minimum_size=settings.compression_min_size
    )

# 2. Rate Limiting
app.add_middleware(
    RateLimitMiddleware,
    requests=settings.rate_limit_requests,
    window=settings.rate_limit_window,
    enabled=settings.rate_limit_enabled
)

# 3. CORS (last, to handle CORS for all responses)
print(f"CORS origins configured: {settings.cors_origins_list}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=False,  # Must be False when using "*"
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(world_router)
app.include_router(chunk_router)
app.include_router(block_router)
app.include_router(biome_router)
app.include_router(upload_router)
app.include_router(resource_router)
app.include_router(isometric_router)


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "description": settings.api_description,
        "docs": "/docs",
        "redoc": "/redoc",
        "resources": {
            "worlds": {
                "current": "/api/worlds/current",
                "health": "/api/worlds/health"
            },
            "chunks": {
                "get_chunk": "/api/chunks/{chunk_x}/{chunk_z}?mode=heightmap",
                "area_heightmap": "/api/chunks/area/heightmap?x1=0&z1=0&x2=100&z2=100",
                "tile": "/api/chunks/tile/{tile_x}/{tile_z}?size=16",
                "viewport_render": "/api/chunks/viewport/render?center_x=0&center_z=0&view_distance=4"
            },
            "blocks": {
                "get_block": "/api/blocks/{block_x}/{block_y}/{block_z}"
            },
            "upload": {
                "world": "/api/upload/world (POST multipart/form-data)"
            },
            "resources": {
                "images": "/api/resources/images/{image}",
                "json": "/api/resources/json?id=diamond_block?namespace=minecraft?properties={}"
            }
        }
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle all uncaught exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": str(exc),
            "detail": "Internal server error"
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower()
    )
