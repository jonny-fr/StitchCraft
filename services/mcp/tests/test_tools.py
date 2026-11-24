import pytest
from fastapi.testclient import TestClient
from stitchcraft_api.app import create_app

from .samples import TINY, corpus

pytestmark = pytest.mark.anyio


async def call(client, name, **arguments):
    result = await client.call_tool(name, arguments)
    return result


async def test_lists_exactly_the_four_tools_with_schemas(client):
    tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"validate_pattern", "parse_pattern", "render_preview", "list_stitches"}
    assert "text" in tools["validate_pattern"].input_schema["properties"]
    assert tools["render_preview"].input_schema["properties"]["view"]["enum"] == [
        "front",
        "side",
        "top",
        "iso",
    ]
    assert tools["list_stitches"].input_schema["required"] == ["dialect"]


@pytest.mark.parametrize(
    ("expected", "text", "dialect"),
    [
        ("de", corpus("de", "01-kugel.txt"), "auto"),
        ("en-US", corpus("en-US", "01-sphere.txt"), "auto"),
        ("en-UK", "Row 1: ch 11, turn\nRow 2: 10 htr, turn", "auto"),
        ("en-UK", corpus("en-UK", "01-sphere.txt"), "en-UK"),
    ],
)
async def test_validate_detects_dialect_and_counts_rows(client, expected, text, dialect):
    r = await call(client, "validate_pattern", text=text, dialect=dialect)
    out = r.structured_content
    assert not r.is_error
    assert out["dialect"] == expected
    assert all(d["code"] != "W_AMBIGUOUS_DIALECT" for d in out["diagnostics"])
    assert all(row["matches"] for row in out["rows"])
    assert out["rows"][0]["line"] == 1


async def test_validate_ambiguous_us_uk_warns_in_both_languages(client):
    text = "Rnd 1: 12 dc in MR (12)\nRnd 2: 24 tr (24)"
    de = (await call(client, "validate_pattern", text=text)).structured_content
    en = (await call(client, "validate_pattern", text=text, ui_locale="en")).structured_content
    d_de = next(d for d in de["diagnostics"] if d["code"] == "W_AMBIGUOUS_DIALECT")
    d_en = next(d for d in en["diagnostics"] if d["code"] == "W_AMBIGUOUS_DIALECT")
    assert d_de["span"] is None
    assert d_en["line"] is None
    assert "en-US, en-UK" in d_de["message"]
    assert d_de["message"].startswith("Die Anleitung kann US- oder UK-Begriffe")
    assert d_en["message"].startswith("The pattern may use US or UK terms (en-US, en-UK).")
    assert "{{" not in d_de["message"] + d_en["message"]


async def test_validate_count_mismatch_has_position_and_actual_vs_expected(client):
    text = "Rd. 1: 6 fM in MR (6)\nRd. 2: 6x zun (13)"
    out = (await call(client, "validate_pattern", text=text, dialect="de")).structured_content
    d = next(d for d in out["diagnostics"] if d["code"] == "E_COUNT_MISMATCH")
    assert (d["line"], d["col"]) == (2, 1)
    assert d["message"] == "Runde/Reihe 2: 12 Maschen gezählt, angegeben sind 13."
    en = (
        await call(client, "validate_pattern", text=text, dialect="de", ui_locale="en")
    ).structured_content
    assert next(x for x in en["diagnostics"] if x["code"] == "E_COUNT_MISMATCH")["message"] == (
        "Round/row 2: counted 12 stitches, pattern says 13."
    )
    assert out["ok"] is False
    assert out["rows"][1]["actual"] == 12
    assert out["rows"][1]["expected"] == 13
    assert out["rows"][1]["matches"] is False


async def test_validate_syntax_error_line_in_message(client):
    out = (
        await call(
            client, "validate_pattern", text="Rd. 1: 6 fM in MR (6)\nRd. 2: ?? (6)", dialect="de"
        )
    ).structured_content
    d = next(d for d in out["diagnostics"] if d["code"] == "E_SYNTAX")
    assert d["message"] == "Zeile 2: unverständliche Anweisung."


@pytest.mark.parametrize(
    "arguments",
    [
        {"text": TINY, "dialect": "klingon"},
        {"text": TINY, "ui_locale": "fr"},
        {"text": "x" * 200_001},
        {"text": TINY, "pace": "turbo"},
        {"text": TINY, "stitches_per_minute": 0},
        {"text": TINY, "params": {"yarn_mm": 0}},
        {"text": TINY, "params": {"needle": 3}},
    ],
)
async def test_validate_rejects_bad_input(client, arguments):
    r = await client.call_tool("validate_pattern", arguments)
    assert r.is_error


SPHERE = corpus("de", "01-kugel.txt")


@pytest.mark.parametrize(
    "timing",
    [
        {},
        {"pace": "anfaenger"},
        {"pace": "schnell", "params": {"yarn_mm": 5.0, "material": "mohair"}},
        {"stitches_per_minute": 15},
    ],
)
async def test_validate_time_estimate_matches_the_api(client, tmp_path, timing):
    """H2: the MCP tool and POST /api/v1/validate give the same estimate for the same input."""
    api = TestClient(create_app(cache_dir=tmp_path))
    expected = api.post("/api/v1/validate", json={"text": SPHERE, "dialect": "de", **timing})
    out = await call(client, "validate_pattern", text=SPHERE, dialect="de", **timing)
    est = out.structured_content["time_estimate"]
    assert est == expected.json()["time_estimate"]
    rows = out.structured_content["rows"]
    assert est["seconds_low"] < est["seconds_high"] and len(est["per_row"]) == len(rows)


async def test_validate_time_estimate_follows_the_pace(client):
    def high(r):
        return r.structured_content["time_estimate"]["seconds_high"]

    normal = await call(client, "validate_pattern", text=SPHERE)
    slow = await call(client, "validate_pattern", text=SPHERE, pace="anfaenger")
    assert high(slow) > high(normal)
    empty = await call(client, "validate_pattern", text="")
    assert empty.structured_content["time_estimate"] is None


async def test_parse_returns_ir_and_diagnostics(client):
    out = (await call(client, "parse_pattern", text=TINY, dialect="de")).structured_content
    assert out["pattern"]["dialect"] == "de"
    assert out["pattern"]["parts"]
    assert out["diagnostics"] == []


@pytest.mark.parametrize("dialect", ["de", "en-US", "en-UK"])
async def test_list_stitches_per_dialect(client, dialect):
    out = (await call(client, "list_stitches", dialect=dialect)).structured_content
    assert out["dialect"] == dialect
    assert out["stitches"]["sc"]
    assert {w["canonical"] for w in out["vocabulary"]} >= {"sc"}


async def test_list_stitches_unknown_dialect_is_error(client):
    r = await client.call_tool("list_stitches", {"dialect": "fr"})
    assert r.is_error
    assert "unknown dialect" in r.content[0].text
