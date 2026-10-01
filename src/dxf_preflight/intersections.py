"""Budgeted same-layer segment-interior checks with exact dyadic orientation.

DXF coordinates have already been parsed as finite Python floats by ezdxf.
Every binary float is an exact integer / power-of-two rational. Scaling the
coordinates to a common power-of-two denominator makes orientation predicates
integer-exact, including near-collinear inputs; no epsilon guess is used.
"""

from collections import defaultdict
from fractions import Fraction
import math

MAX_COORDINATE_BITS = 4096


def inspect_intersections(segments, *, max_pairs: int, max_findings: int) -> tuple[dict, list[dict]]:
    summary = {
        "status": "checked", "x_overlap_candidate_pairs": 0, "exact_pair_tests": 0,
        "coverage": "supported same-layer straight segments only",
        "arithmetic": "exact dyadic integer predicates on ezdxf-parsed binary float coordinates",
        "intersection_point_display": "approximate float coordinates; predicate classification is exact on parsed values",
    }
    findings = []
    layers = defaultdict(list)
    for segment in segments:
        layers[segment.layer.casefold()].append(segment)

    def incomplete(reason):
        summary["status"] = "unknown"
        summary["reason"] = reason
        findings.append({
            "rule_id": "SCOPE007", "severity": "blocker",
            "message": "Segment-interior checks are unknown because a resource or numeric limit was reached.",
            "details": {"phase": "segment_intersections", "reason": reason},
        })
        return summary, findings

    for name in sorted(layers):
        edges = layers[name]
        points = {p for edge in edges for p in (edge.start, edge.end)}
        ratios = {point: [v.as_integer_ratio() for v in point] for point in points}
        exponent = max((denominator.bit_length() - 1 for r in ratios.values() for _, denominator in r), default=0)
        exact = {
            p: tuple(numerator << (exponent - (denominator.bit_length() - 1)) for numerator, denominator in r)
            for p, r in ratios.items()
        }
        if any(abs(v).bit_length() > MAX_COORDINATE_BITS for p in exact.values() for v in p):
            return incomplete("exact coordinate integer range exceeded")
        records = sorted(
            [(min(e.start[0], e.end[0]), max(e.start[0], e.end[0]),
              min(e.start[1], e.end[1]), max(e.start[1], e.end[1]), i, e)
             for i, e in enumerate(edges)], key=lambda r: (r[0], r[1], r[4])
        )
        for i, left in enumerate(records):
            for j in range(i + 1, len(records)):
                right = records[j]
                if right[0] > left[1]:
                    break
                summary["x_overlap_candidate_pairs"] += 1
                if summary["x_overlap_candidate_pairs"] > max_pairs:
                    return incomplete("X-overlap candidate-pair budget exceeded")
                if right[2] > left[3] or left[2] > right[3]:
                    continue
                summary["exact_pair_tests"] += 1
                first, second = left[5], right[5]
                a, b, c, d = (exact[p] for p in (first.start, first.end, second.start, second.end))
                o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
                o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
                detail = {"segments": [first.ref, second.ref]}
                if _opposite(o1, o2) and _opposite(o3, o4):
                    point = _intersection_point(a, b, c, d, exponent)
                    if not all(math.isfinite(v) for v in point):
                        return incomplete("intersection-point display numeric range exceeded")
                    rule = "INTER001"
                    message = "Exact interior crossing between same-layer straight segments. Operation intent is not inferred."
                    detail.update({"point": point, "point_is_approximate": True})
                elif o1 == o2 == o3 == o4 == 0:
                    axis = 0 if a[0] != b[0] else 1
                    lo = max(min(a[axis], b[axis]), min(c[axis], d[axis]))
                    hi = min(max(a[axis], b[axis]), max(c[axis], d[axis]))
                    if lo >= hi:
                        continue  # No positive-length overlap; shared endpoint is legal.
                    all_points = [first.start, first.end, second.start, second.end]
                    overlap = [next(list(p) for p in all_points if exact[p][axis] == end) for end in (lo, hi)]
                    rule = "INTER003"
                    message = "Exact positive-length collinear overlap between same-layer segments. Operation intent is not inferred."
                    detail["overlap_endpoints"] = overlap
                else:
                    contacts = []
                    for orientation, point, start, end, display in (
                        (o1, c, a, b, second.start), (o2, d, a, b, second.end),
                        (o3, a, c, d, first.start), (o4, b, c, d, first.end),
                    ):
                        if orientation == 0 and _inside(point, start, end) and point != start and point != end:
                            if list(display) not in contacts:
                                contacts.append(list(display))
                    if not contacts:
                        continue  # Legal adjacent/shared endpoints, or disjoint segments.
                    rule = "INTER002"
                    message = "A same-layer segment endpoint lies exactly in another segment's interior (T/contact). Operation intent is not inferred."
                    detail["contact_points"] = contacts
                if len(findings) >= max_findings:
                    return incomplete("intersection finding-report budget exceeded")
                findings.append({"rule_id": rule, "severity": "error", "message": message, "details": detail})
    return summary, findings


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _opposite(a, b):
    return (a < 0 < b) or (b < 0 < a)


def _inside(point, start, end):
    return all(min(start[axis], end[axis]) <= point[axis] <= max(start[axis], end[axis]) for axis in (0, 1))


def _intersection_point(a, b, c, d, exponent):
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    q = (c[0] - a[0], c[1] - a[1])
    denominator = r[0] * s[1] - r[1] * s[0]
    numerator = q[0] * s[1] - q[1] * s[0]
    return [float(Fraction(a[axis] * denominator + numerator * r[axis], denominator * (1 << exponent))) for axis in (0, 1)]
