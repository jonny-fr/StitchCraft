import io
import json
import struct
import time

import numpy as np
import pytest
from conftest import reference_pattern

from stitchcraft_core.export import decode_yarn_bin, encode_yarn_bin, glb_bytes, shape_json
from stitchcraft_core.params import Params
from stitchcraft_core.pipeline import cache_key, preview


@pytest.fixture(scope="module")
def disc():
    return preview(reference_pattern("2-disc"), "de", Params())


def test_preview_reports_stats(disc):
    assert disc.stats["stitches"] == 126
    assert disc.stats["rows"] == 6
    w, d, h = disc.stats["size_cm"]
    assert 5.0 < max(w, d) < 7.0  # 6 rounds of 5 mm stitches -> ~6 cm disc
    assert disc.ok


def test_yarn_bin_roundtrip(disc):
    blob = encode_yarn_bin(disc.yarn)
    assert blob[:4] == b"SCYN"
    back = decode_yarn_bin(blob)
    assert np.allclose(back["points"], disc.yarn.points, atol=1e-5)
    assert np.array_equal(back["stitch_ids"], disc.yarn.stitch_ids)
    assert list(back["segment_offsets"]) == [0]


def test_glb_carries_stitch_ids(disc):
    blob = glb_bytes(disc.yarn, sides=6)
    assert blob[:4] == b"glTF"
    n = struct.unpack("<I", blob[12:16])[0]
    gltf = json.loads(blob[20 : 20 + n])
    assert "_STITCH_ID" in gltf["meshes"][0]["primitives"][0]["attributes"]
    import trimesh

    scene = trimesh.load(io.BytesIO(blob), file_type="glb")
    assert len(scene.geometry) == 1


def test_shape_json_links_stitches_to_source(disc):
    data = shape_json(disc)
    first = data["stitches"][1]
    assert set(first) >= {"id", "row", "type", "span", "position", "parents"}
    assert first["span"]["line"] == 1
    assert len(data["rows"]) == 6


def test_cache_key_ignores_formatting_but_not_params():
    a = cache_key("Rd. 1: 6 fM in MR (6)", "de", Params())
    b = cache_key("Rd. 1:   6 fM  in MR (6)", "de", Params())
    c = cache_key("Rd. 1: 6 fM in MR (6)", "de", Params(fill=0.2))
    assert a == b
    assert a != c


def test_preview_is_deterministic():
    """A8: same input + seed -> identical yarn path."""
    text = reference_pattern("4-cup")
    a = preview(text, "de", Params())
    b = preview(text, "de", Params())
    assert a.yarn_hash == b.yarn_hash


def test_sphere_preview_under_five_seconds():
    """A9: ~450-stitch ball previews in < 5 s on the CPU."""
    text = reference_pattern("3-sphere")
    preview("6 fM in MR", "de", Params())  # warm caches (grammar, data)
    t0 = time.perf_counter()
    p = preview(text, "de", Params())
    elapsed = time.perf_counter() - t0
    assert p.stats["stitches"] == 432
    assert elapsed < 5.0, elapsed
