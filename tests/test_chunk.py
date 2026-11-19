import time
import logging
import requests
import pytest
from datetime import datetime

from utilities.mock_api import api_available, api_without_world

LOGGER = logging.getLogger(__name__)
BASE_URL = "http://localhost:8001/api/chunks"

class TestChunkEndpoints:
    @pytest.fixture(autouse=True)
    def setup(self, api_available):
        """Setup for each test - verify API is reachable."""
        pass

    # ==================== CONTENT TYPE TESTS ====================
    def test_endpoints_return_json(self):
        """Test endpoints return application/json content type."""
        endpoints = ["/0/0/0", "/current"]
        
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            content_type = response.headers.get("content-type", "")
            
            assert "application/json" in content_type.lower(), \
                f"Endpoint {endpoint} should return JSON, got: {content_type}"
    # ==================== SUCCESSFUL RESPONSE TESTS ====================
    """Endpoint {chunk_x}/{chunk_z}/{chunk_h}"""
    def test_get_chunk_endpoint_mode_heightmap(self):
        """Test /chunk endpoint returns valid response for given coordinates."""
        x = 0
        z = 0
        h = 0
        params = {"mode": "heightmap"}
        response = requests.get(f"{BASE_URL}/{x}/{z}/{h}", params=params)

        LOGGER.debug(f"Request params: {params}")
        LOGGER.debug(f"Request URL: {response.url}")
        LOGGER.debug(f"Response status code: {response.status_code}")

        if response.status_code == 503:
            pytest.skip("World is not loaded - cannot test loaded state")

        assert response.status_code == 200, "Expected status code 200"

        data = response.json()
        LOGGER.debug(f"Response data: {data}")

        assert "data" in data, "Response JSON should contain 'data' key"
        chunk_data = data["data"]
        assert isinstance(chunk_data, dict), "'data' should be a dictionary"
        assert chunk_data["chunk_x"] is not None, "'data' should contain 'chunk_x' key"
        assert chunk_data["chunk_z"] is not None, "'data' should contain 'chunk_z' key"
        assert chunk_data["heightmap"] is not None, "'data' should contain 'heightmap' key"
        assert chunk_data["surface_blocks"] is None, "'data' should not contain 'heightmap' key"
    
    def test_get_chunk_endpoint_mode_surface(self):
        """Test /chunk endpoint returns valid response for given coordinates."""
        x = 0
        z = 0
        h = 0
        params = {"mode": "surface"}
        response = requests.get(f"{BASE_URL}/{x}/{z}/{h}", params=params)

        LOGGER.debug(f"Request params: {params}")
        LOGGER.debug(f"Request URL: {response.url}")
        LOGGER.debug(f"Response status code: {response.status_code}")

        if response.status_code == 503:
            pytest.skip("World is not loaded - cannot test loaded state")

        assert response.status_code == 200, "Expected status code 200"

        data = response.json()
        LOGGER.debug(f"Response data: {data}")

        assert "data" in data, "Response JSON should contain 'data' key"
        chunk_data = data["data"]
        assert isinstance(chunk_data, dict), "'data' should be a dictionary"    
        assert chunk_data["chunk_x"] is not None, "'data' should contain 'chunk_x' key"
        assert chunk_data["chunk_z"] is not None, "'data' should contain 'chunk_z' key"
        assert chunk_data["heightmap"] is None, "'data' should not contain 'heightmap' key"
        assert chunk_data["surface_blocks"] is not None, "'data' should contain 'heightmap' key"

    def test_get_chunk_endpoint_mode_isometric(self):
        """Test /chunk endpoint returns valid response for given coordinates."""
        x = 0
        z = 0
        h = 0
        params = {"mode": "isometric"}
        response = requests.get(f"{BASE_URL}/{x}/{z}/{h}", params=params)

        LOGGER.debug(f"Request params: {params}")
        LOGGER.debug(f"Request URL: {response.url}")
        LOGGER.debug(f"Response status code: {response.status_code}")

        if response.status_code == 503:
            pytest.skip("World is not loaded - cannot test loaded state")

        assert response.status_code == 200, "Expected status code 200"

        data = response.json()
        LOGGER.debug(f"Response data: {data}")

        assert "data" in data, "Response JSON should contain 'data' key"
        chunk_data = data["data"]
        assert chunk_data["chunk_x"] is not None, "'data' should contain 'chunk_x' key"
        assert chunk_data["chunk_z"] is not None, "'data' should contain 'chunk_z' key"
        assert chunk_data["heightmap"] is not None, "'data' should contain 'heightmap' key"
        assert chunk_data["surface_blocks"] is not None, "'data' should contain 'heightmap' key"

    def test_get_chunk_endpoint_mode_render(self):
        """Test /chunk endpoint returns valid response for given coordinates."""
        x = 0
        z = 0
        h = 0
        params = {"mode": "render"}
        response = requests.get(f"{BASE_URL}/{x}/{z}/{h}", params=params)

        LOGGER.debug(f"Request params: {params}")
        LOGGER.debug(f"Request URL: {response.url}")
        LOGGER.debug(f"Response status code: {response.status_code}")

        if response.status_code == 503:
            pytest.skip("World is not loaded - cannot test loaded state")

        assert response.status_code == 200, "Expected status code 200"

        data = response.json()
        LOGGER.debug(f"Response data: {data}")

        assert "data" in data, "Response JSON should contain 'data' key"
        chunk_data = data["data"]
        assert isinstance(chunk_data, dict), "'data' should be a dictionary"
        assert chunk_data["chunk_x"] is not None, "'data' should contain 'chunk_x' key"
        assert chunk_data["chunk_z"] is not None, "'data' should contain 'chunk_z' key"
        assert chunk_data["render_data"] is not None, "'data' should contain 'render_data' key"
        assert chunk_data["heightmap"] is None, "'data' should not contain 'heightmap' key"
        assert chunk_data["surface_blocks"] is None, "'data' should not contain 'heightmap' key"

    # ==================== ERROR HANDLING TESTS ====================
    """Endpoint {chunk_x}/{chunk_z}/{chunk_h}"""

    def test_get_chunk_endpoint_mode_invalid(self):
        """Test /chunk endpoint returns valid resonse for invalid mode"""
        x = 0
        z = 0
        h = 0
        params = {"mode": "invalid_mode"}
        response = requests.get(f"{BASE_URL}/{x}/{z}/{h}", params=params)

        LOGGER.debug(f"Request params: {params}")
        LOGGER.debug(f"Request URL: {response.url}")
        LOGGER.debug(f"Response status code: {response.status_code}")
        LOGGER.debug(f"Response data: {response.text}")

        assert response.status_code == 422, "Expected status code 422"
    
    def test_get_chunk_unknown_chunks(self):
        """Test chunk valid chunks coordinates."""
        x = 100
        z = 100
        h = 0
        params = {"mode": "heightmap"}
        response = requests.get(f"{BASE_URL}/{x}/{z}/{h}", params=params)

        if response.status_code == 503:
            pytest.skip("World is not loaded - cannot test loaded state")

        assert response.status_code == 404, "Expected status code 404"

    def test_get_chunk_endpoint_no_world(self, api_without_world):
        """Test /chunk endpoint when no world is loaded - expect 503."""
        x = 0
        z = 0
        h = 0
        params = {"mode": "heightmap"}
        response = requests.get(f"{api_without_world}/api/chunks/{x}/{z}/{h}", params=params)

        LOGGER.debug(f"Request params: {params}")
        LOGGER.debug(f"Request URL: {response.url}")
        LOGGER.debug(f"Response status code: {response.status_code}")
        LOGGER.debug(f"Response data: {response.text}")

        assert response.status_code == 503, "Expected status code 503"

    # ==================== RESPONSE TIME TESTS ====================
    # ==================== CONSISTENCY TESTS ====================
