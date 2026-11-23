import socket
import subprocess
import sys
import time

import anyio
import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

pytestmark = pytest.mark.anyio
TOOLS = {"validate_pattern", "parse_pattern", "render_preview", "list_stitches"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_stdio_initialize_and_list_tools(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "stitchcraft_mcp.server", "stdio"],
        env={"STITCHCRAFT_CACHE": str(tmp_path)},
    )
    async with Client(params) as client:
        assert {t.name for t in (await client.list_tools()).tools} == TOOLS


async def test_http_initialize_and_list_tools(tmp_path):
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "stitchcraft_mcp.server", "http", "--port", str(port)],
        env={**__import__("os").environ, "STITCHCRAFT_CACHE": str(tmp_path)},
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            await anyio.sleep(0.1)
        async with Client(f"http://127.0.0.1:{port}/mcp") as client:
            assert {t.name for t in (await client.list_tools()).tools} == TOOLS
    finally:
        proc.terminate()
        proc.wait(timeout=10)
