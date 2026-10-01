import pytest

from dxf_preflight.core import Segment
from dxf_preflight.intersections import inspect_intersections


def segment(a, b, *, layer="CUT", handle="1"):
    return Segment(tuple(map(float, a)), tuple(map(float, b)), layer, handle, 0)


def inspect(*edges, max_pairs=250000, max_findings=256):
    return inspect_intersections(edges, max_pairs=max_pairs, max_findings=max_findings)


@pytest.mark.parametrize("reverse_first,reverse_second", [(False, False), (False, True), (True, False), (True, True)])
def test_proper_crossing_is_direction_invariant(reverse_first, reverse_second):
    a = [(0, 0), (10, 10)]
    b = [(0, 10), (10, 0)]
    if reverse_first: a.reverse()
    if reverse_second: b.reverse()
    summary, findings = inspect(segment(*a), segment(*b, handle="2"))
    assert summary["status"] == "checked"
    assert [f["rule_id"] for f in findings] == ["INTER001"]
    assert findings[0]["details"]["point"] == [5, 5]


def test_t_contact_is_detected_without_extending_segment():
    _, findings = inspect(segment((0, 0), (10, 0)), segment((5, 0), (5, 5), handle="2"))
    assert [f["rule_id"] for f in findings] == ["INTER002"]
    assert findings[0]["details"]["contact_points"] == [[5, 0]]
    assert not inspect(segment((0, 0), (10, 0)), segment((15, 0), (15, 5)))[1]


@pytest.mark.parametrize("first,second", [
    (((0, 0), (10, 0)), ((10, 0), (10, 10))),
    (((0, 0), (10, 0)), ((10, 0), (20, 0))),
    (((0, 0), (10, 0)), ((0, 1e-15), (10, 1e-15))),
    (((0, 0), (0, 10)), ((1, 0), (1, 10))),
    (((0, 0), (1e8, 1e8 + 1)), ((5e7, 5e7 + 0.5 + 1e-8), (15e7, 15e7 + 1.5 + 1e-8))),
])
def test_legal_shared_endpoints_parallel_and_near_collinear_do_not_false_positive(first, second):
    summary, findings = inspect(segment(*first), segment(*second))
    assert summary["status"] == "checked"
    assert not findings


@pytest.mark.parametrize("first,second,overlap", [
    (((0, 0), (10, 0)), ((5, 0), (15, 0)), [[5, 0], [10, 0]]),
    (((0, 0), (10, 10)), ((8, 8), (2, 2)), [[2, 2], [8, 8]]),
    (((0, 10), (0, 0)), ((0, 5), (0, 15)), [[0, 5], [0, 10]]),
])
def test_positive_collinear_overlap_is_reported(first, second, overlap):
    _, findings = inspect(segment(*first), segment(*second))
    assert [f["rule_id"] for f in findings] == ["INTER003"]
    assert findings[0]["details"]["overlap_endpoints"] == overlap


def test_cross_layer_intersection_is_not_conflated():
    summary, findings = inspect(segment((0, 0), (10, 10)), segment((0, 10), (10, 0), layer="ETCH"))
    assert summary["status"] == "checked" and not findings


@pytest.mark.parametrize("size", [1e300, 5e-324])
def test_exact_orientation_survives_float_overflow_or_underflow(size):
    _, findings = inspect(segment((-size, 0), (size, 0)), segment((0, -size), (0, size)))
    assert [f["rule_id"] for f in findings] == ["INTER001"]
    assert findings[0]["details"]["point"] == [0, 0]


@pytest.mark.parametrize("budget", ["pairs", "findings", "coordinate_bits"])
def test_budget_or_numeric_uncertainty_is_unknown_not_clear(budget, monkeypatch):
    if budget == "coordinate_bits":
        from dxf_preflight import intersections
        monkeypatch.setattr(intersections, "MAX_COORDINATE_BITS", 1)
    summary, findings = inspect(
        segment((0, 0), (10, 10)), segment((0, 10), (10, 0)),
        max_pairs=0 if budget == "pairs" else 250000,
        max_findings=0 if budget == "findings" else 256,
    )
    assert summary["status"] == "unknown"
    assert findings[-1]["rule_id"] == "SCOPE007"


def test_default_pair_budget_bounds_x_overlapping_y_disjoint_worst_case():
    edges = [segment((0, row), (100, row), handle=str(row)) for row in range(709)]
    summary, findings = inspect(*edges)
    assert summary["status"] == "unknown"
    assert summary["x_overlap_candidate_pairs"] == 250001
    assert summary["exact_pair_tests"] == 0
    assert findings[-1]["rule_id"] == "SCOPE007"
