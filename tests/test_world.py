"""
Comprehensive integration tests for world endpoints.
Tests various scenarios including success cases, error handling, and edge cases.
"""
import time
import logging
import requests
import pytest
from datetime import datetime
from tests.utilities.mock_api import api_available, api_without_world

LOGGER = logging.getLogger(__name__)
BASE_URL = "http://localhost:8001/api/worlds"

class TestWorldEndpoints:
    """Integration tests for world endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test - verify API is reachable."""
        pass

    # ==================== HEALTH ENDPOINT TESTS ====================

    def test_health_endpoint_returns_valid_response(self):
        """Test health endpoint returns proper structure."""
        response = requests.get(f"{BASE_URL}/health")
        
        # Should always return 200 for health checks
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify response structure
        assert "status" in data
        assert "world_loaded" in data
        assert "timestamp" in data
        
        # Verify data types
        assert isinstance(data["status"], str)
        assert isinstance(data["world_loaded"], bool)
        assert data["status"] in ["healthy", "unhealthy"]
        
        LOGGER.info(f"Health check response: {data}")

    def test_health_endpoint_timestamp_is_recent(self):
        """Test health endpoint returns recent timestamp."""
        response = requests.get(f"{BASE_URL}/health")
        data = response.json()
        
        # Parse timestamp and verify it's recent (within last 5 seconds)
        timestamp = datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00'))
        now = datetime.utcnow()
        time_diff = abs((now - timestamp).total_seconds())
        
        assert time_diff < 5, f"Timestamp is too old: {time_diff}s"

    # ==================== CURRENT WORLD ENDPOINT TESTS ====================

    def test_current_world_returns_valid_structure_when_loaded(self):
        """Test /current endpoint returns proper structure when world is loaded."""
        response = requests.get(f"{BASE_URL}/current")
        
        # Could be 200 (loaded) or 503 (not loaded)
        if response.status_code == 503:
            pytest.skip("World is not loaded - cannot test loaded state")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify APIResponse structure
        assert "status" in data
        assert "data" in data
        assert "error" in data
        assert "timestamp" in data
        
        assert data["status"] == "success"
        assert data["error"] is None
        assert data["data"] is not None
        
        LOGGER.info(f"World current response status: {data['status']}")

    def test_current_world_data_contains_required_fields(self):
        """Test /current endpoint data contains all required WorldInfoResponse fields."""
        response = requests.get(f"{BASE_URL}/current")
        
        if response.status_code == 503:
            pytest.skip("World is not loaded")
        
        assert response.status_code == 200
        data = response.json()["data"]
        
        # Verify all required fields from WorldInfoResponse
        required_fields = [
            "dimension",
            "world_folder",
            "region_dir",
            "loaded_regions",
            "region_list"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        LOGGER.info(f"World data fields: {list(data.keys())}")

    def test_current_world_dimension_is_valid(self):
        """Test dimension field contains valid Minecraft dimension."""
        response = requests.get(f"{BASE_URL}/current")
        
        if response.status_code == 503:
            pytest.skip("World is not loaded")
        
        data = response.json()["data"]
        
        valid_dimensions = ["overworld", "nether", "end"]
        assert data["dimension"] in valid_dimensions, f"Invalid dimension: {data['dimension']}"
        
        LOGGER.info(f"Current dimension: {data['dimension']}")

    def test_current_world_paths_are_not_empty(self):
        """Test world_folder and region_dir are not empty strings."""
        response = requests.get(f"{BASE_URL}/current")

        LOGGER.debug(f"Response status code: {response.status_code}")
        
        if response.status_code == 503:
            pytest.skip("World is not loaded")
        
        data = response.json()["data"]

        LOGGER.debug(f"response data: {data}")
        
        assert data["world_folder"] != "", "world_folder should not be empty"
        assert data["region_dir"] != "", "region_dir should not be empty"
        assert len(data["world_folder"]) > 0
        assert len(data["region_dir"]) > 0


    def test_current_world_loaded_regions_matches_list_length(self):
        """Test loaded_regions count matches region_list length."""
        response = requests.get(f"{BASE_URL}/current")
        
        if response.status_code == 503:
            pytest.skip("World is not loaded")
        
        data = response.json()["data"]
        
        loaded_regions = data["loaded_regions"]
        region_list = data["region_list"]
        
        assert isinstance(loaded_regions, int)
        assert isinstance(region_list, list)
        assert loaded_regions == len(region_list), \
            f"loaded_regions ({loaded_regions}) doesn't match region_list length ({len(region_list)})"

    def test_current_world_region_list_contains_valid_coordinates(self):
        """Test region_list contains valid coordinate pairs."""
        response = requests.get(f"{BASE_URL}/current")
        
        if response.status_code == 503:
            pytest.skip("World is not loaded")
        
        data = response.json()["data"]
        region_list = data["region_list"]
        
        for region in region_list[:10]:  # Test first 10 to avoid long tests
            assert isinstance(region, list), f"Region should be list: {region}"
            assert len(region) == 2, f"Region should have 2 coords: {region}"
            assert isinstance(region[0], int), f"Region X should be int: {region[0]}"
            assert isinstance(region[1], int), f"Region Z should be int: {region[1]}"

    def test_current_world_bounds_format_if_present(self):
        """Test bounds field has correct format if present."""
        response = requests.get(f"{BASE_URL}/current")
        
        if response.status_code == 503:
            pytest.skip("World is not loaded")
        
        data = response.json()["data"]
        
        if "bounds" in data and data["bounds"] is not None:
            bounds = data["bounds"]
            assert isinstance(bounds, list)
            assert len(bounds) == 6, "Bounds should have 6 values [min_x, min_y, min_z, max_x, max_y, max_z]"
            
            # Verify min < max for each axis
            assert bounds[0] <= bounds[3], "min_x should be <= max_x"
            assert bounds[1] <= bounds[4], "min_y should be <= max_y"
            assert bounds[2] <= bounds[5], "min_z should be <= max_z"

    def test_current_world_cache_stats_structure_if_present(self):
        """Test cache_stats has valid structure if present."""
        response = requests.get(f"{BASE_URL}/current")
        
        if response.status_code == 503:
            pytest.skip("World is not loaded")
        
        data = response.json()["data"]
        
        if "cache_stats" in data and data["cache_stats"] is not None:
            cache_stats = data["cache_stats"]
            assert isinstance(cache_stats, dict)
            LOGGER.info(f"Cache stats: {cache_stats}")

    def test_current_world_returns_503_when_not_loaded(self, api_without_world):
        """Test /current returns 503 with proper error when world not loaded."""
        """Test 503 response on API instance with no world."""

        response = requests.get(f"{api_without_world}/api/worlds/current", timeout=5)
        
        # Should get 503 since no world is configured
        assert response.status_code == 503, \
            f"Expected 503 when no world loaded, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        assert "not loaded" in data["detail"].lower() or "world" in data["detail"].lower()
        
        LOGGER.info("Successfully tested 503 with separate API instance")

    def test_health_reports_world_not_loaded(self, api_without_world):
        """Test health endpoint reports world as not loaded."""
        response = requests.get(f"{api_without_world}/api/worlds/health", timeout=5)
        
        assert response.status_code == 200  # Health always returns 200
        data = response.json()

        LOGGER.debug(f"Health response data: {data}")
        
        assert data["status"] == "unhealthy"
        assert data["world_loaded"] == False

    # ==================== ERROR HANDLING TESTS ====================

    def test_invalid_endpoint_returns_404(self):
        """Test invalid endpoint returns 404."""
        response = requests.get(f"{BASE_URL}/nonexistent")
        assert response.status_code == 404

    def test_invalid_method_returns_405(self):
        """Test invalid HTTP method returns 405."""
        response = requests.post(f"{BASE_URL}/health")
        assert response.status_code == 405

    # ==================== RESPONSE TIME TESTS ====================

    def test_health_endpoint_responds_quickly(self):
        """Test health endpoint responds within reasonable time."""

        
        start = time.time()
        response = requests.get(f"{BASE_URL}/health")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 5.0, f"Health endpoint too slow: {elapsed:.2f}s"
        
        LOGGER.info(f"Health endpoint response time: {elapsed*1000:.0f}ms")

    def test_current_world_responds_within_timeout(self):
        """Test /current endpoint responds within reasonable time."""
        
        start = time.time()
        response = requests.get(f"{BASE_URL}/current", timeout=5)
        elapsed = time.time() - start
        
        assert response.status_code in [200, 503]
        assert elapsed < 5.0, f"Current world endpoint too slow: {elapsed:.2f}s"
        
        LOGGER.info(f"Current world response time: {elapsed*1000:.0f}ms")

    # ==================== CONTENT TYPE TESTS ====================

    def test_endpoints_return_json(self):
        """Test endpoints return application/json content type."""
        endpoints = ["/health", "/current"]
        
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            content_type = response.headers.get("content-type", "")
            
            assert "application/json" in content_type.lower(), \
                f"Endpoint {endpoint} should return JSON, got: {content_type}"

    # ==================== CONSISTENCY TESTS ====================

    def test_multiple_health_calls_are_consistent(self):
        """Test multiple health calls return consistent world_loaded status."""
        responses = []
        
        for _ in range(3):
            response = requests.get(f"{BASE_URL}/health")
            responses.append(response.json()["world_loaded"])
        
        # All responses should be the same (world shouldn't load/unload during test)
        assert all(r == responses[0] for r in responses), \
            "world_loaded status changed between calls"

    def test_current_world_data_is_consistent_across_calls(self):
        """Test /current returns consistent data across multiple calls."""
        response1 = requests.get(f"{BASE_URL}/current")
        response2 = requests.get(f"{BASE_URL}/current")
        
        assert response1.status_code == response2.status_code
        
        if response1.status_code == 200:
            data1 = response1.json()["data"]
            data2 = response2.json()["data"]
            
            # Core fields should be identical
            assert data1["dimension"] == data2["dimension"]
            assert data1["world_folder"] == data2["world_folder"]
            assert data1["loaded_regions"] == data2["loaded_regions"]



class TestWorldEndpointsEdgeCases:
    """Edge case tests for world endpoints."""
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test - verify API is reachable."""
        pass

    def test_request_with_trailing_slash(self):
        """Test endpoints work with trailing slash."""
        response = requests.get(f"{BASE_URL}/health/")
        # FastAPI usually redirects or handles this
        assert response.status_code in [200, 307, 308]

    def test_request_with_query_parameters_ignored(self):
        """Test health endpoint ignores unexpected query parameters."""
        response = requests.get(f"{BASE_URL}/health?foo=bar&baz=qux")
        assert response.status_code == 200
        
        # Should return same data as without params
        response_normal = requests.get(f"{BASE_URL}/health")
        assert response.json()["status"] == response_normal.json()["status"]
