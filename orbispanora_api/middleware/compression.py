"""
Gzip compression middleware for JSON responses.
Provides ~60-70% size reduction for JSON data.
Excludes documentation pages to avoid breaking Swagger UI.
"""

from starlette.middleware.gzip import GZipMiddleware as StarletteGZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


class GZipMiddleware(StarletteGZipMiddleware):
    """
    Custom GZip middleware that excludes documentation endpoints.
    Prevents compression of Swagger UI assets which can break the interface.
    """

    def __init__(self, app: ASGIApp, minimum_size: int = 500, compresslevel: int = 6):
        super().__init__(app, minimum_size=minimum_size, compresslevel=compresslevel)
        # Paths to exclude from compression
        self.exclude_paths = ["/docs", "/redoc", "/openapi.json"]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Check if path should be excluded
        if scope["type"] == "http":
            path = scope.get("path", "")
            # Exclude docs and static assets
            if any(path.startswith(exclude) for exclude in self.exclude_paths):
                # Skip compression for these paths
                await self.app(scope, receive, send)
                return

        # Apply compression for other paths
        await super().__call__(scope, receive, send)
