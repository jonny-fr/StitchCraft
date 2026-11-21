from conftest import reference_pattern
from stitchcraft_core.graph import build_graph
from stitchcraft_core.notation import parse


def graph(text: str, dialect: str = "de"):
    return build_graph(parse(text, dialect=dialect).pattern)


def counting(g, row):
    return [n for n in row.node_ids if g.nodes[n].counting]


def test_reference_counts_match_pattern(piece):
    """A3: stitch count per round/row in the model equals the pattern."""
    text = reference_pattern(piece)
    g = graph(text)
    assert [d.code for d in g.diagnostics if d.severity != "info"] == []
    for row in g.rows:
        if row.expected is not None:
            assert len(counting(g, row)) == row.expected, f"row {row.number}"


def test_reference_parent_counts_are_correct(piece):
    """A3: every stitch has the correct number of parents."""
    g = graph(reference_pattern(piece))
    for node in g.nodes:
        if node.type == "ring" or node.turning or (node.type == "ch" and node.row == 0):
            continue
        expected = 2 if node.op == "dec" else 1
        assert len(node.parents) == expected, node


def test_magic_ring_children():
    g = graph("6 fM in MR (6)")
    assert g.ring is not None
    assert [g.nodes[n].parents for n in counting(g, g.rows[0])] == [[g.ring]] * 6


def test_increase_puts_two_stitches_into_one_parent():
    g = graph("6 fM in MR\n6x zun (12)")
    r1 = counting(g, g.rows[0])
    r2 = counting(g, g.rows[1])
    assert [g.nodes[n].parents for n in r2] == [[p] for p in r1 for _ in range(2)]


def test_decrease_consumes_two_parents():
    g = graph("6 fM in MR\n6x zun (12)\n6x abn (6)")
    r2 = counting(g, g.rows[1])
    r3 = counting(g, g.rows[2])
    assert g.nodes[r3[0]].parents == r2[0:2]
    assert g.nodes[r3[5]].parents == r2[10:12]


def test_spiral_round_continues_in_yarn_order():
    g = graph("6 fM in MR\nfM rundum (6)")
    r1 = counting(g, g.rows[0])
    r2 = counting(g, g.rows[1])
    assert [g.nodes[n].parents[0] for n in r2] == r1


def test_turned_row_works_back_along_previous_row():
    g = graph("R 1: 6 Lm, wenden\nR 2: 5 fM, 1 Lm, wenden (5)\nR 3: 5 fM (5)")
    r2 = counting(g, g.rows[1])
    r3 = counting(g, g.rows[2])
    assert [g.nodes[n].parents[0] for n in r3] == list(reversed(r2))
    assert [g.rows[i].side for i in range(3)] == [1, 1, -1]


def test_first_chain_from_hook_is_skipped():
    g = graph("R 1: 6 Lm, wenden\nR 2: 5 fM (5)")
    chains = g.rows[0].node_ids
    r2 = counting(g, g.rows[1])
    assert [g.nodes[n].parents[0] for n in r2] == list(reversed(chains))[1:]


def test_turning_chain_is_not_counted_and_not_a_parent():
    g = graph("R 1: 6 Lm, wenden\nR 2: 5 fM, 1 Lm, wenden (5)\nR 3: 5 fM (5)")
    turning = [n for n in g.rows[1].node_ids if g.nodes[n].turning]
    assert len(turning) == 1
    assert all(turning[0] not in g.nodes[n].parents for n in g.rows[2].node_ids)


def test_count_mismatch_is_reported_with_params():
    g = graph("6 fM in MR\n6x zun (13)")
    (d,) = [d for d in g.diagnostics if d.code == "E_COUNT_MISMATCH"]
    assert d.params == {"row": 2, "expected": 13, "actual": 12}
    assert d.span.line == 2


def test_too_few_parents_is_reported():
    g = graph("6 fM in MR\n8 fM (8)")
    assert "E_TOO_FEW_PARENTS" in [d.code for d in g.diagnostics]


def test_unworked_stitches_are_warned():
    g = graph("6 fM in MR\n4 fM (4)")
    (d,) = [d for d in g.diagnostics if d.code == "W_UNWORKED"]
    assert d.params == {"row": 2, "left": 2}


def test_back_loop_is_recorded_on_nodes():
    g = graph(reference_pattern("4-cup"))
    row6 = next(r for r in g.rows if r.number == 6)
    assert {g.nodes[n].loop for n in row6.node_ids} == {"blo"}


def test_sphere_has_expected_size():
    g = graph(reference_pattern("3-sphere"))
    assert sum(n.counting for n in g.nodes) == 432
