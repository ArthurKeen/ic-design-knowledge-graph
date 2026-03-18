"""
tests/conftest.py — Shared pytest fixtures.

Provides the `arango_docker` fixture: spins up a throwaway ArangoDB container
on a dynamically assigned free port, waits until it is healthy, and tears it
down after the test session.  No manual port configuration required.

Usage in a test:

    def test_something(arango_docker):
        db = arango_docker          # python-arango Database handle
        db.collection("foo")...
"""

import os
import socket
import subprocess
import time

import pytest
from arango import ArangoClient

# Use the locally cached community image (confirmed present on this host).
ARANGO_IMAGE = os.getenv("TEST_ARANGO_IMAGE", "arangodb:3.12")
TEST_DB_NAME = "ic_kg_test"
TEST_ROOT_PASSWORD = "testroot"


def _free_port() -> int:
    """Return an OS-assigned free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_arango(host: str, port: int, timeout: int = 120) -> None:
    """Block until ArangoDB is reachable (200 or 401 on /_api/version)."""
    import urllib.request
    import urllib.error

    url = f"http://{host}:{port}/_api/version"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except urllib.error.HTTPError as exc:
            # 401 means the server is up but requires auth — that's healthy
            if exc.code == 401:
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"ArangoDB did not become healthy on {host}:{port} within {timeout}s")


@pytest.fixture(scope="session")
def arango_docker():
    """
    Session-scoped fixture that provisions a fresh ArangoDB container.

    Yields a python-arango ``Database`` object connected to a clean test DB.
    The container is removed (--rm) when the session ends.
    """
    port = _free_port()
    container_name = f"ic_kg_test_{port}"

    cmd = [
        "docker", "run",
        "--rm",
        "--name", container_name,
        "-d",
        "-p", f"{port}:8529",
        "-e", f"ARANGO_ROOT_PASSWORD={TEST_ROOT_PASSWORD}",
        ARANGO_IMAGE,
    ]

    print(f"\n[conftest] Starting ArangoDB container on port {port} …")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip(f"docker run failed (Docker not available?): {result.stderr[:200]}")

    container_id = result.stdout.strip()

    try:
        _wait_for_arango("localhost", port, timeout=120)
        print(f"[conftest] ArangoDB healthy on localhost:{port}")

        client = ArangoClient(hosts=f"http://localhost:{port}")
        sys_db = client.db("_system", username="root", password=TEST_ROOT_PASSWORD)

        if not sys_db.has_database(TEST_DB_NAME):
            sys_db.create_database(TEST_DB_NAME)

        db = client.db(TEST_DB_NAME, username="root", password=TEST_ROOT_PASSWORD)

        # Expose connection params as attributes so tests can build their own clients
        db._test_host = f"http://localhost:{port}"
        db._test_port = port
        db._test_password = TEST_ROOT_PASSWORD
        db._test_dbname = TEST_DB_NAME

        yield db

    finally:
        print(f"\n[conftest] Stopping container {container_name} …")
        subprocess.run(["docker", "rm", "-f", container_name],
                       capture_output=True, timeout=15)
