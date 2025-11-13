"""
Custom exceptions for the API.
"""

from fastapi import HTTPException, status


class APIError(HTTPException):
    """Base API error."""
    
    def __init__(self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        super().__init__(status_code=status_code, detail=message)


class WorldNotLoadedError(APIError):
    """Raised when world is not loaded."""
    
    def __init__(self, message: str = "World is not loaded"):
        super().__init__(message, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


class ChunkNotFoundError(APIError):
    """Raised when chunk is not found."""
    
    def __init__(self, chunk_x: int, chunk_z: int):
        message = f"Chunk ({chunk_x}, {chunk_z}) not found"
        super().__init__(message, status_code=status.HTTP_404_NOT_FOUND)


class BlockNotFoundError(APIError):
    """Raised when block is not found."""
    
    def __init__(self, x: int, y: int, z: int):
        message = f"Block at ({x}, {y}, {z}) not found"
        super().__init__(message, status_code=status.HTTP_404_NOT_FOUND)


class InvalidParameterError(APIError):
    """Raised when parameter is invalid."""
    
    def __init__(self, message: str):
        super().__init__(message, status_code=status.HTTP_400_BAD_REQUEST)
