import pytest
import requests
import time
import os
import subprocess
import sys
import logging

LOGGER = logging.getLogger(__name__)

@pytest.fixture(scope="session")
def api_available():
    """Session-level fixture to check if API is available."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(f"http://localhost:8001/api/worlds/health", timeout=5)
            if response.status_code in [200, 503]:
                LOGGER.info("API is available for testing")
                return True
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                pytest.exit(f"API not available after {max_retries} attempts: {e}")
            time.sleep(1)
    return False

@pytest.fixture(scope="module")
def api_without_world():
    """
    Start a separate API instance without a world loaded.
    This is the most reliable way to test 503 scenarios.
    """

    # Find API directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Navigate from utilities/ -> tests/ -> api/ 
    api_dir = os.path.dirname(os.path.dirname(current_dir))
    
    # Start API on different port without world
    env = os.environ.copy()
    env["API_PORT"] = "8002"  # Different port
    env["WORLD_PATH"] = ""     # No world
    env["PYTHONUNBUFFERED"] = "1"
    
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", 
        "--port", "8002", "--log-level", "error"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=api_dir
    )
    
    # Wait for server to start
    api_ready = False
    for _ in range(50):  # 5 second timeout
        try:
            resp = requests.get("http://127.0.0.1:8002/", timeout=1)
            if resp.status_code < 500:
                api_ready = True
                break
        except:
            pass
        time.sleep(0.1)
    
    if not api_ready:
        process.terminate()
        process.wait()
        pytest.skip("Could not start separate API instance")
    
    yield "http://127.0.0.1:8002"
    
    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()