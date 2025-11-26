import os
import sys
import subprocess
import time
import requests
import pytest


API_HOST = "127.0.0.1"
API_PORT = 8001
API_URL = f"http://{API_HOST}:{API_PORT}"


def wait_for_server(url, process, timeout=30):
    """Wait for the FastAPI server to be ready before running tests."""
    print(f"Waiting for API to be ready at {url}...")
    
    start_time = time.time()
    for i in range(timeout * 10):
        # Check if process has died
        if process.poll() is not None:
            # Process has terminated
            stdout, stderr = process.communicate()
            print("\n[ERROR] API process died!")
            print(f"Exit code: {process.returncode}")
            print(f"\nSTDOUT:\n{stdout.decode('utf-8', errors='ignore')}")
            print(f"\nSTDERR:\n{stderr.decode('utf-8', errors='ignore')}")
            raise RuntimeError("API process terminated unexpectedly")
        
        try:
            r = requests.get(url, timeout=1)
            if r.status_code < 500:
                elapsed = time.time() - start_time
                print(f"API is ready! (took {elapsed:.2f}s)")
                return True
        except requests.exceptions.ConnectionError:
            pass
        except requests.exceptions.Timeout:
            pass
        
        # Print progress every 5 seconds
        if i % 50 == 0 and i > 0:
            elapsed = time.time() - start_time
            print(f"Still waiting... ({elapsed:.1f}s elapsed)")
        
        time.sleep(0.1)
    
    # Timeout reached - capture output for debugging
    print("\n[ERROR] Timeout waiting for API to start!")
    if process.poll() is None:
        print("Process is still running but not responding...")
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=3)
            print(f"\nSTDOUT:\n{stdout.decode('utf-8', errors='ignore')}")
            print(f"\nSTDERR:\n{stderr.decode('utf-8', errors='ignore')}")
        except subprocess.TimeoutExpired:
            process.kill()
    
    raise RuntimeError(f"API did not respond at {url} after {timeout}s")


@pytest.fixture(scope="session", autouse=True)
def start_api():
    """
    Launch FastAPI server (uvicorn) in a separate process
    and terminate it cleanly at the end of the test session.
    """
    print("\n[*] Starting OrbisPanora API for integration tests...")
    print(f"[*] Python executable: {sys.executable}")
    print(f"[*] Working directory: {os.getcwd()}")

    # Find the API directory (where main.py is located)
    # This handles both pytest from command line and VS Code test runner
    current_dir = os.path.dirname(os.path.abspath(__file__))
    api_dir = os.path.dirname(current_dir)  # Go up from tests/ to api/
    
    # Verify main.py exists
    main_py_path = os.path.join(api_dir, "main.py")
    if not os.path.exists(main_py_path):
        raise RuntimeError(f"Could not find main.py at {main_py_path}")
    
    #print(f"[*] API directory: {api_dir}")

    env = os.environ.copy()
    env["ENV"] = "test"
    env["CACHE_ENABLED"] = "false"
    env["RATE_LIMIT_ENABLED"] = "false"
    env["COMPRESSION_ENABLED"] = "false"
    env["API_PORT"] = str(API_PORT)
    env["API_HOST"] = API_HOST
    env["PYTHONUNBUFFERED"] = "1"  # Force unbuffered output

    # Use Python module syntax for cross-platform compatibility
    process = subprocess.Popen(
        [
            sys.executable,  # Use the current Python interpreter
            "-m", "uvicorn",
            "main:app",
            "--host", API_HOST,
            "--port", str(API_PORT),
            "--log-level", "info"  # Changed to info to see startup messages
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=api_dir  # Use the detected API directory
    )

    try:
            # Always attempt startup
        try:
            wait_for_server(f"{API_URL}/docs", process)
        except RuntimeError as e:
            print(f"\n[!] Failed to start API: {e}")
            raise

        # Yield to run all tests
        yield

    finally:
        # ALWAYS clean up — even if startup failed or tests aborted
        print("\n[*] Stopping OrbisPanora API...")

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
                print("[*] API stopped gracefully")
            except subprocess.TimeoutExpired:
                print("[!] Process didn't stop gracefully, forcing kill...")
                process.kill()
                process.wait()
                print("[*] API killed")
            else:
                print("[*] API process was already dead")