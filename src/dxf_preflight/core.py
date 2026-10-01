"""Geometry extraction delegates DXF parsing to ezdxf; no input write APIs."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import math
from pathlib import Path
import stat
import tempfile

import ezdxf
from ezdxf import units

from . import __version__
from .intersections import inspect_intersections

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_SEGMENTS = 10_000
MAX_ENTITIES = 20_000
MAX_COMPARISONS = 1_000_000
MAX_SEGMENT_PAIR_CANDIDATES = 250_000
MAX_INTERSECTION_FINDINGS = 256
EXPECTED_UNITS = {"in": 1, "ft": 2, "mm": 4, "cm": 5, "m": 6}
DISCLAIMER = (
    "Limited read-only metadata, endpoint-graph and same-layer straight-segment checks only. This is not a "
    "complete manufacturability review, cutting-safety assessment, toolpath "
    "validation, CAM certification, or supplier acceptance. Verify in CAD/CAM "
    "and with your fabricator before production."
)
NOT_CHECKED = [
    "Cross-layer crossings/overlaps, near-intersections, tolerance-based line-on-edge snapping",
    "Near-duplicate segments and operation/intent interpretation of coincident geometry",
    "Contour winding, nesting, hole/island meaning, bridges, minimum features",
    "Actual intended 1:1 scale or physical dimensions (INSUNITS is a declaration)",
    "Material, stock thickness, kerf, process tolerances, tooling and cut safety",
    "Complete DXF structural validity, CAD display styling and plot behavior",
]


@dataclass(frozen=True)
class Segment:
    start: tuple[float, float]
    end: tuple[float, float]
    layer: str
    entity: str
    part: int
    style: dict = field(default_factory=dict)

    @property
    def ref(self) -> dict:
        return {"handle": self.entity, "segment_index": self.part, "layer": self.layer, "style": self.style, "operation_inferred": False}

    @property
    def key(self) -> tuple:
        # No rounding: direction is normalized, coordinates remain exact.
        return (self.layer.casefold(), *sorted((self.start, self.end)))


def _finding(report: dict, rule: str, severity: str, message: str, **details) -> None:
    report["findings"].append(
        {"rule_id": rule, "severity": severity, "message": message, "details": details}
    )


def _finish(report: dict, unreadable: bool = False) -> dict:
    if not any(f["severity"] == "blocker" for f in report["findings"]) and any(state != "checked" for state in report["checks"].values()):
        _finding(report, "SCOPE009", "blocker", "Required limited checks did not all complete; this report cannot be clear.")
    counts = Counter(f["severity"] for f in report["findings"])
    report["summary"]["finding_counts"] = {
        key: counts[key] for key in ("blocker", "error", "warning")
    }
    report["coverage_complete_for_declared_subset"] = not counts["blocker"] and not unreadable
    report["status"] = (
        "unreadable" if unreadable else
        "incomplete" if counts["blocker"] else
        "issues_found" if report["findings"] else
        "limited_checks_clear"
    )
    return report


def _new_report(path: Path, tolerance: float, expected_unit: str | None) -> dict:
    """One conservative report shape, including paths where parsing never runs."""
    return {
        "schema_version": "1.1", "tool": {"name": "dxf-preflight", "version": __version__, "ezdxf_version": ezdxf.__version__},
        "input": {"path": str(path), "sha256": None, "unchanged_during_analysis": None},
        "read_only": True, "manual_review_required": True, "gate_eligible": False, "status": None,
        "parameters": {"endpoint_tolerance": tolerance, "tolerance_unit": "drawing units", "expected_unit": expected_unit},
        "execution": {"mode": "in_process", "wall_clock_timeout_seconds": None, "hard_memory_limit": False, "hard_cpu_limit": False, "sandboxed": False},
        "checks": {name: "not_run" for name in ("input_read", "parsing", "units", "scope", "segment_extraction", "duplicates", "topology", "segment_intersections", "input_integrity")},
        "scope": {"entities": ["2D LINE", "zero-bulge, zero-width LWPOLYLINE"], "layout": "modelspace", "plane": "exact WCS XY / default OCS, z=0", "limits": {"max_file_bytes": MAX_FILE_BYTES, "max_entities": MAX_ENTITIES, "max_segments": MAX_SEGMENTS, "max_endpoint_comparisons": MAX_COMPARISONS, "max_segment_pair_candidates": MAX_SEGMENT_PAIR_CANDIDATES, "max_intersection_findings": MAX_INTERSECTION_FINDINGS}},
        "disclaimer": DISCLAIMER, "not_checked": NOT_CHECKED[:], "findings": [],
        "summary": {"modelspace_entities": 0, "supported_entities": 0, "unsupported_entities": 0, "extracted_segments": 0, "unique_nondegenerate_segments": 0, "layers": [], "segment_intersections": {"status": "not_run"}},
    }


def _segments(entity, report: dict) -> list[Segment] | None:
    """Return None for unsupported geometry; never approximate arcs or OCS."""
    kind = entity.dxftype()
    ref = {"handle": str(entity.dxf.get("handle", "?")), "entity_type": kind}
    if kind not in {"LINE", "LWPOLYLINE"}:
        _finding(report, "SCOPE001", "blocker", "Unsupported modelspace entity.", **ref)
        return None
    layer = str(entity.dxf.get("layer", "0"))
    style = {
        "entity_color": entity.dxf.get("color", 256),
        "entity_true_color": entity.dxf.get("true_color", None),
        "entity_linetype": entity.dxf.get("linetype", "BYLAYER"),
        "entity_lineweight": entity.dxf.get("lineweight", -1),
    }
    if entity.doc is not None and entity.doc.layers.has_entry(layer):
        layer_entry = entity.doc.layers.get(layer)
        style.update({
            "layer_color": layer_entry.dxf.get("color", 7),
            "layer_true_color": layer_entry.dxf.get("true_color", None),
            "layer_linetype": layer_entry.dxf.get("linetype", "Continuous"),
            "layer_lineweight": layer_entry.dxf.get("lineweight", -3),
        })
    style = {key: _json_metadata(value) for key, value in style.items()}
    ref["layer"] = layer
    extrusion = tuple(float(v) for v in entity.dxf.get("extrusion", (0, 0, 1)))
    thickness = float(entity.dxf.get("thickness", 0))
    if extrusion != (0.0, 0.0, 1.0) or thickness != 0.0:
        _finding(report, "SCOPE002", "blocker", "Non-default extrusion or nonzero thickness.",
                 **ref, extrusion=[_json_number(v) for v in extrusion], thickness=_json_number(thickness))
        return None
    if kind == "LINE":
        start = tuple(float(v) for v in entity.dxf.start)
        end = tuple(float(v) for v in entity.dxf.end)
        values = (*start, *end)
        if not all(math.isfinite(v) for v in values):
            _finding(report, "GEOM001", "blocker", "Non-finite geometry coordinates.", **ref)
            return None
        # XY-plane membership is exact; endpoint tolerance does not flatten 3D.
        if start[2] != 0.0 or end[2] != 0.0:
            _finding(report, "SCOPE002", "blocker", "LINE is not exactly in the WCS XY plane.", **ref)
            return None
        return [Segment(start[:2], end[:2], layer, ref["handle"], 0, style)]

    if len(entity) > MAX_SEGMENTS + 1:
        _finding(report, "SCOPE007", "blocker", "Polyline vertex count exceeds the prototype limit.", **ref)
        return None
    elevation = float(entity.dxf.get("elevation", 0))
    points = [tuple(float(v) for v in p) for p in entity.get_points("xyseb")]
    constant_width = float(entity.dxf.get("const_width", 0))
    if not all(math.isfinite(v) for p in points for v in p) or not all(
        math.isfinite(v) for v in (elevation, constant_width)
    ):
        _finding(report, "GEOM001", "blocker", "Non-finite polyline coordinates or attributes.", **ref)
        return None
    if elevation != 0.0:
        _finding(report, "SCOPE002", "blocker", "LWPOLYLINE has nonzero OCS elevation.", **ref)
        return None
    if any(p[4] != 0.0 for p in points):
        _finding(report, "SCOPE003", "blocker", "LWPOLYLINE bulge is unsupported; no arc flattening.", **ref)
        return None
    if constant_width != 0.0 or any(p[2] != 0.0 or p[3] != 0.0 for p in points):
        _finding(report, "SCOPE004", "blocker", "LWPOLYLINE widths are unsupported.", **ref)
        return None
    flags = int(entity.dxf.get("flags", 0))
    if flags & ~(1 | 128):
        _finding(report, "SCOPE004", "blocker", "Unknown LWPOLYLINE flags.", **ref, flags=flags)
        return None
    if len(points) < 2:
        _finding(report, "GEOM002", "error", "Polyline has fewer than two vertices.", **ref)
        return []
    vertices = [p[:2] for p in points]
    pairs = list(zip(vertices, vertices[1:]))
    if entity.closed:
        pairs.append((vertices[-1], vertices[0]))
    return [Segment(a, b, layer, ref["handle"], i, style) for i, (a, b) in enumerate(pairs)]


def _json_number(value: float):
    return value if math.isfinite(value) else str(value)


def _json_metadata(value):
    """Preserve malformed metadata as safe text, without treating it as valid."""
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float:
        return _json_number(value)
    return repr(value)


class _BudgetExceeded(Exception):
    pass


def _topology(segments: list[Segment], tolerance: float, report: dict) -> None:
    """Layer-isolated endpoint graph. Intersections along segment interiors excluded."""
    layers = defaultdict(list)
    for segment in segments:
        layers[segment.layer.casefold()].append(segment)
    if len(layers) > 1:
        _finding(report, "LAYER001", "warning", "Geometry spans multiple layers; connectivity is checked separately per layer.",
                 layers=sorted({s.layer for s in segments}))
    comparisons = 0
    layer_summaries = []
    for name in sorted(layers):
        edges = layers[name]
        points = sorted({p for edge in edges for p in (edge.start, edge.end)})
        parents = list(range(len(points)))

        def root(i):
            while parents[i] != i:
                parents[i] = parents[parents[i]]
                i = parents[i]
            return i

        buckets = defaultdict(list)
        near_pairs = 0
        # Exact-point collapse happens above. This avoids a quadratic pile of
        # identical endpoint comparisons. Neighboring buckets avoid rounding gaps.
        for i, point in enumerate(points):
            cell = (math.floor(point[0] / tolerance), math.floor(point[1] / tolerance))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in buckets[(cell[0] + dx, cell[1] + dy)]:
                        comparisons += 1
                        if comparisons > MAX_COMPARISONS:
                            raise _BudgetExceeded
                        if math.dist(point, points[j]) <= tolerance:
                            near_pairs += 1
                            a, b = root(i), root(j)
                            parents[max(a, b)] = min(a, b)
            buckets[cell].append(i)
        clusters = defaultdict(list)
        for i in range(len(points)):
            clusters[root(i)].append(i)
        # A-B and B-C proximity must never silently connect A-C when A-C > tol.
        ambiguous = []
        for cluster in clusters.values():
            bad = False
            for offset, i in enumerate(cluster):
                for j in cluster[offset + 1:]:
                    comparisons += 1
                    if comparisons > MAX_COMPARISONS:
                        raise _BudgetExceeded
                    if math.dist(points[i], points[j]) > tolerance:
                        bad = True
                        break
                if bad:
                    break
            if bad:
                ambiguous.append([list(points[i]) for i in cluster[:8]])
        if ambiguous:
            _finding(report, "TOPO004", "blocker", "Ambiguous transitive tolerance cluster; this layer's endpoint topology was not classified.",
                     layer=edges[0].layer, clusters=ambiguous)
            layer_summaries.append({"layer": edges[0].layer, "status": "incomplete", "unique_segments": len(edges)})
            continue
        if near_pairs:
            _finding(report, "TOPO003", "warning", "Distinct endpoints were connected within tolerance; inspect these small gaps manually.",
                     layer=edges[0].layer, tolerance=tolerance, nearby_pair_count=near_pairs,
                     clusters=[[list(points[i]) for i in c] for c in clusters.values() if len(c) > 1])
        lookup = {p: root(i) for i, p in enumerate(points)}
        degree = Counter()
        adjacency = defaultdict(set)
        refs = defaultdict(list)
        for edge in edges:
            a, b = lookup[edge.start], lookup[edge.end]
            degree[a] += 1
            degree[b] += 1
            adjacency[a].add(b)
            adjacency[b].add(a)
            refs[a].append(edge.ref)
            refs[b].append(edge.ref)
        open_nodes = [i for i in sorted(degree) if degree[i] == 1]
        branch_nodes = [i for i in sorted(degree) if degree[i] > 2]
        if open_nodes:
            _finding(report, "TOPO001", "error", "Open-chain endpoints found in the supported endpoint graph.",
                     layer=edges[0].layer,
                     endpoints=[{"point": list(points[i]), "entities": refs[i]} for i in open_nodes])
        if branch_nodes:
            _finding(report, "TOPO002", "error", "Branch/shared endpoint nodes found (degree greater than two).",
                     layer=edges[0].layer,
                     nodes=[{"point": list(points[i]), "degree": degree[i], "entities": refs[i]} for i in branch_nodes])
        seen = set()
        components = 0
        cycle_components = 0
        for node in sorted(degree):
            if node in seen:
                continue
            stack = [node]
            component = set()
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                component.add(current)
                stack.extend(adjacency[current] - seen)
            components += 1
            cycle_components += all(degree[i] == 2 for i in component)
        layer_summaries.append({
            "layer": edges[0].layer, "status": "checked",
            "unique_segments": len(edges), "endpoint_nodes": len(degree),
            "components": components, "degree_two_cycle_components": cycle_components,
            "open_endpoint_count": len(open_nodes), "branch_node_count": len(branch_nodes),
        })
    report["summary"]["layers"] = layer_summaries


def _capture_bytes(path: Path) -> bytes:
    with path.open("rb") as stream:
        return stream.read(MAX_FILE_BYTES + 1)


def _analyze(path: str | Path, *, tolerance: float = 1e-6, expected_unit: str | None = None, _on_snapshot=None) -> dict:
    """Inspect a file without saving/modifying it. Tolerance is in drawing units."""
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be finite and greater than zero")
    if expected_unit is not None and expected_unit not in EXPECTED_UNITS:
        raise ValueError(f"expected_unit must be one of {sorted(EXPECTED_UNITS)}")
    path = Path(path)
    report = _new_report(path, tolerance, expected_unit)
    snapshot = None
    try:
        file_stat = path.stat()
        if not stat.S_ISREG(file_stat.st_mode):
            _finding(report, "FILE001", "blocker", "Input must be a regular file, not a device, directory or pipe.")
            return _finish(report, unreadable=True)
        if file_stat.st_size > MAX_FILE_BYTES:
            _finding(report, "SCOPE007", "blocker", "Input exceeds the prototype's file-size limit.")
            return _finish(report)
        original = _capture_bytes(path)
        if len(original) > MAX_FILE_BYTES:
            _finding(report, "SCOPE007", "blocker", "Input exceeds the prototype's file-size limit.")
            return _finish(report)
        report["input"]["sha256"] = hashlib.sha256(original).hexdigest()
        report["checks"]["input_read"] = "checked"
        if _on_snapshot is not None:
            _on_snapshot(report["input"]["sha256"])
        report["checks"]["parsing"] = "unknown"
        # Parse exactly the captured bytes whose hash is in the report. ezdxf's
        # normal readfile() encoding/binary detection remains unchanged. The
        # original DXF is never a parser write target. CLI TMPDIR is parent-owned
        # so the supervisor can remove snapshots even after killing its worker.
        with tempfile.TemporaryDirectory(prefix="dxf-preflight-snapshot-") as directory:
            snapshot = Path(directory) / "captured.dxf"
            snapshot.write_bytes(original)
            doc = ezdxf.readfile(snapshot, errors="strict")
    except (OSError, ezdxf.DXFError, UnicodeError, ValueError, IndexError) as exc:
        # Parser errors must refer to the caller's source, not the random private
        # snapshot path, so unchanged unreadable input still gives stable reports.
        reason = str(exc).replace(str(snapshot), str(path)) if snapshot is not None else str(exc)
        _finding(report, "FILE001", "blocker", "Input could not be read as DXF; no recovery or audit was run.",
                 exception_type=type(exc).__name__, reason=reason)
        return _finish(report, unreadable=True)

    report["checks"]["parsing"] = "checked"
    report["input"]["dxf_version"] = doc.dxfversion
    code = doc.header.get("$INSUNITS", None)
    safe_code = _json_metadata(code)
    unit_name = units.unit_name(code) if type(code) is int and 0 <= code <= 24 else "Unknown"
    report["units"] = {"source": "$INSUNITS", "code": safe_code, "raw_value_type": type(code).__name__, "name": unit_name, "expected": expected_unit, "scaled_or_inferred": False}
    if code is None or code == 0 or type(code) is not int or code not in range(1, 25):
        _finding(report, "UNIT001", "blocker", "Drawing units are missing, unitless or unrecognized; expected-unit does not fill or repair metadata.", declared_code=safe_code, declared_type=type(code).__name__)
    elif expected_unit is not None and code != EXPECTED_UNITS[expected_unit]:
        _finding(report, "UNIT002", "error", "Declared INSUNITS differs from the explicitly expected unit; no scaling was applied.",
                 declared_code=code, expected_code=EXPECTED_UNITS[expected_unit])
    report["checks"]["units"] = "checked"
    for layout in doc.layouts:
        if layout.name != "Model" and len(layout):
            _finding(report, "SCOPE005", "blocker", "Paperspace content is outside the supported scope.", layout=layout.name, entity_count=len(layout))
    for block in doc.blocks:
        if not block.is_any_layout:
            _finding(report, "SCOPE005", "blocker", "Block definition is unsupported, including empty or unreferenced blocks.", block=block.name, entity_count=len(block))

    segments = []
    scan_complete = True
    for entity in doc.modelspace():
        if report["summary"]["modelspace_entities"] >= MAX_ENTITIES:
            _finding(report, "SCOPE007", "blocker", "Modelspace entity count exceeds the prototype limit; the remaining entities were not inspected.")
            scan_complete = False
            break
        report["summary"]["modelspace_entities"] += 1
        try:
            extracted = _segments(entity, report)
        except (ValueError, TypeError, AttributeError, IndexError) as exc:
            _finding(report, "SCOPE008", "blocker", "Entity attributes could not be interpreted conservatively.",
                     handle=str(entity.dxf.get("handle", "?")), exception_type=type(exc).__name__)
            extracted = None
        if extracted is None:
            report["summary"]["unsupported_entities"] += 1
        else:
            report["summary"]["supported_entities"] += 1
            segments.extend(extracted)
        if len(segments) > MAX_SEGMENTS:
            _finding(report, "SCOPE007", "blocker", "Supported segment count exceeds the prototype limit; geometry checks were not run.")
            scan_complete = False
            break
    report["checks"]["scope"] = "checked" if scan_complete else "unknown"
    report["checks"]["segment_extraction"] = "unknown" if not scan_complete or report["summary"]["unsupported_entities"] else "checked"
    report["summary"]["extracted_segments"] = len(segments)
    if len(segments) <= MAX_SEGMENTS:
        if not segments:
            _finding(report, "GEOM003", "error", "No supported line segments were extracted.")
        unique = {}
        duplicate_groups = defaultdict(list)
        for segment in segments:
            if math.dist(segment.start, segment.end) <= tolerance:
                _finding(report, "GEOM002", "error", "Segment length is at or below endpoint tolerance; omitted from topology.",
                         entity=segment.ref, start=list(segment.start), end=list(segment.end))
                continue
            duplicate_groups[segment.key].append(segment)
            unique.setdefault(segment.key, segment)
        for group in duplicate_groups.values():
            if len(group) > 1:
                _finding(report, "DUP001", "error", "Exact same-layer geometric coincidence (direction-normalized); operation intent is not inferred and deletion is not advised.",
                         segments=[s.ref for s in group], start=list(group[0].start), end=list(group[0].end))
        report["summary"]["unique_nondegenerate_segments"] = len(unique)
        report["checks"]["duplicates"] = "checked" if scan_complete else "unknown"
        try:
            _topology(list(unique.values()), tolerance, report)
            report["checks"]["topology"] = "unknown" if not scan_complete or any(layer["status"] != "checked" for layer in report["summary"]["layers"]) else "checked"
        except (_BudgetExceeded, OverflowError):
            _finding(report, "SCOPE007", "blocker", "Endpoint analysis exceeded its comparison or numeric range limit; topology is incomplete.")
            report["checks"]["topology"] = "unknown"
        intersection_summary, intersection_findings = inspect_intersections(
            list(unique.values()), max_pairs=MAX_SEGMENT_PAIR_CANDIDATES, max_findings=MAX_INTERSECTION_FINDINGS
        )
        if not scan_complete:
            intersection_summary["status"] = "unknown"
        report["summary"]["segment_intersections"] = intersection_summary
        report["checks"]["segment_intersections"] = intersection_summary["status"]
        report["findings"].extend(intersection_findings)
    try:
        with path.open("rb") as stream:
            final_bytes = stream.read(MAX_FILE_BYTES + 1)
        final_digest = hashlib.sha256(final_bytes).hexdigest()
        report["input"]["unchanged_during_analysis"] = final_digest == report["input"]["sha256"]
        report["checks"]["input_integrity"] = "checked" if report["input"]["unchanged_during_analysis"] else "unknown"
        if not report["input"]["unchanged_during_analysis"]:
            _finding(report, "FILE002", "blocker", "Input changed during analysis; report is not a stable snapshot.")
    except OSError as exc:
        _finding(report, "FILE002", "blocker", "Input could not be re-read to verify an unchanged file.", reason=str(exc))
        report["checks"]["input_integrity"] = "unknown"
    return _finish(report)


def analyze(path: str | Path, *, tolerance: float = 1e-6, expected_unit: str | None = None) -> dict:
    """Read-only input analysis on captured bytes; no in-process wall deadline.

    The final original-path read is compared with those bytes. It cannot prove
    that the original file remained unchanged between observed read points.
    """
    return _analyze(path, tolerance=tolerance, expected_unit=expected_unit)
