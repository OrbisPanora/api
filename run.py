"""
Quick start script for development.
Run this file to start the API server.
"""

import uvicorn
from config import settings

if __name__ == "__main__":
    print("\nStarting OrbisPanora API in development mode...")
    print(f"Server will run on http://{settings.api_host}:{settings.api_port}")
    print(f"Documentation at http://{settings.api_host}:{settings.api_port}/docs\n")
    
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower()
    )
