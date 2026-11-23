import pytest
from mcp.client import Client
from stitchcraft_mcp.server import create_server


@pytest.fixture()
def cache(tmp_path):
    return tmp_path / "cache"


@pytest.fixture()
async def client(cache):
    async with Client(create_server(cache)) as c:
        yield c
