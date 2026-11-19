"""
OrbisPanora API - FastAPI backend for isometric Minecraft world viewer.
Main application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .middleware import GZipMiddleware, RateLimitMiddleware
from .routers import (
    biome_router,
    block_router,
    chunk_router,
    isometric_router,
    resource_router,
    upload_router,
    world_router,
)
from .routers.isometric import shutdown_isometric_service
from .services import get_world_service
from .services.cache_service import init_cache_service
from .settings import APP_DESCRIPTION, APP_TITLE, APP_VERSION, get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup
    print("\n" + "="*60)
    print("Starting OrbisPanora API")
    print("="*60)

    try:
        for level, message in get_settings().problems():
            print(f"[{level.upper()}] {message}")
            if level == "error":
                raise ValueError(message)

        # Initialize cache service
        if get_settings().cache_enabled:
            ttl_config = {
                "heightmap": get_settings().cache_ttl_heightmap,
                "surface": get_settings().cache_ttl_surface,
                "chunk": get_settings().cache_ttl_chunk
            }
            init_cache_service(
                get_settings().cache_type,
                get_settings().redis_url.get_secret_value(),
                ttl_config
            )
            print(f"Cache service initialized ({get_settings().cache_type})")
            print(f"  - Heightmap TTL: {get_settings().cache_ttl_heightmap}s")
            print(f"  - Surface TTL: {get_settings().cache_ttl_surface}s")
            print(f"  - Chunk TTL: {get_settings().cache_ttl_chunk}s")
        else:
            print("Cache disabled")

        world_service = get_world_service()
        if get_settings().world_path is not None:
            world_service.load_world_from_path(str(get_settings().world_path))
        print("World service initialized")
    except Exception as e:
        print(f"Failed to initialize: {e}")
        raise

    print("="*60)
    print(f"API ready at http://{get_settings().host}:{get_settings().port}")
    print(f"Docs available at http://{get_settings().host}:{get_settings().port}/docs")
    print("="*60 + "\n")

    yield

    # Shutdown
    print("\n" + "="*60)
    print("Shutting down OrbisPanora API")
    print("="*60 + "\n")

    get_world_service().shutdown()
    shutdown_isometric_service()


# Create FastAPI application
app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)


# Configure middlewares
# 1. Compression (first, to compress all responses)
if get_settings().compression_enabled:
    app.add_middleware(
        GZipMiddleware,
        minimum_size=get_settings().compression_min_size
    )

# 2. Rate Limiting
app.add_middleware(
    RateLimitMiddleware,
    requests=get_settings().rate_limit_requests,
    window=get_settings().rate_limit_window,
    enabled=get_settings().rate_limit_enabled
)

# 3. CORS (last, to handle CORS for all responses)
_cors_origins = get_settings().cors_origins
print(f"CORS origins configured: {_cors_origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in _cors_origins else _cors_origins,
    allow_credentials=False,  # Must be False when using "*"
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
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
        "name": APP_TITLE,
        "version": APP_VERSION,
        "description": APP_DESCRIPTION,
        "docs": "/docs",
        "redoc": "/redoc",
        "resources": {
            "worlds": {
                "current": "/api/worlds/current",
                "health": "/api/worlds/health"
            },
            "chunks": {
                "get_chunk": "/api/chunks/{chunk_x}/{chunk_z}/{chunk_h}?mode=heightmap",
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
async def global_exception_handler(_request, exc):
    """Handle all uncaught exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": "Internal server error",
            "detail": "Internal server error"
        }
    )
