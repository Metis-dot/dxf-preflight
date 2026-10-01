from pathlib import Path

import ezdxf
import pytest

from dxf_preflight import analyze
from dxf_preflight import core


@pytest.fixture
def drawing(tmp_path):
    def save(build=None, *, unit=4):
        doc = ezdxf.new("R2010")
        doc.units = unit
        if build:
            build(doc)
        path = tmp_path / "drawing.dxf"
        doc.saveas(path)
        return path
    return save


def rectangle(doc, *, layer="0", shift=0):
    points = [(shift, 0), (shift + 10, 0), (shift + 10, 10), (shift, 10)]
    for a, b in zip(points, points[1:] + points[:1]):
        doc.modelspace().add_line(a, b, dxfattribs={"layer": layer})


def rules(report):
    return {finding["rule_id"] for finding in report["findings"]}


def test_four_lines_form_endpoint_cycle_and_do_not_modify_input(drawing):
    path = drawing(rectangle)
    before = path.read_bytes()
    report = analyze(path, expected_unit="mm")
    assert report["status"] == "limited_checks_clear"
    assert report["coverage_complete_for_declared_subset"] is True
    assert report["manual_review_required"] is True
    assert report["gate_eligible"] is False
    assert report["summary"]["layers"][0]["degree_two_cycle_components"] == 1
    assert report["input"]["unchanged_during_analysis"] is True
    assert report["input"]["dxf_version"] == "AC1024"
    assert path.read_bytes() == before
    assert "cutting-safety" in report["disclaimer"]


@pytest.mark.parametrize("closed,repeated", [(True, False), (False, True)])
def test_polyline_geometry_not_just_closed_flag(drawing, closed, repeated):
    points = [(0, 0), (10, 0), (10, 10), (0, 10)]
    if repeated:
        points.append(points[0])
    report = analyze(drawing(lambda d: d.modelspace().add_lwpolyline(points, close=closed)))
    assert report["status"] == "limited_checks_clear"
    assert report["summary"]["extracted_segments"] == 4


def test_open_polyline_reports_coordinates_and_handle(drawing):
    report = analyze(drawing(lambda d: d.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 10)])))
    assert report["status"] == "issues_found"
    finding = next(f for f in report["findings"] if f["rule_id"] == "TOPO001")
    assert len(finding["details"]["endpoints"]) == 2
    assert finding["details"]["endpoints"][0]["entities"][0]["handle"]


def test_reversed_duplicate_normalized_and_removed_only_from_analysis(drawing):
    def build(doc):
        rectangle(doc)
        doc.modelspace().add_line((10, 0), (0, 0))
    report = analyze(drawing(build))
    assert report["status"] == "issues_found"
    assert rules(report) == {"DUP001"}
    assert report["summary"]["extracted_segments"] == 5
    assert report["summary"]["unique_nondegenerate_segments"] == 4


def test_polyline_segment_and_line_duplicate(drawing):
    def build(doc):
        doc.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
        doc.modelspace().add_line((10, 0), (0, 0))
    assert "DUP001" in rules(analyze(drawing(build)))


def test_coincident_different_styles_preserved_without_operation_inference(drawing):
    def build(doc):
        rectangle(doc)
        doc.modelspace().add_line((10, 0), (0, 0), dxfattribs={"color": 1, "linetype": "DASHED"})
    report = analyze(drawing(build))
    finding = next(f for f in report["findings"] if f["rule_id"] == "DUP001")
    refs = finding["details"]["segments"]
    assert {r["style"]["entity_color"] for r in refs} == {256, 1}
    assert {r["style"]["entity_linetype"] for r in refs} == {"BYLAYER", "DASHED"}
    assert all(r["operation_inferred"] is False for r in refs)
    assert all("layer_color" in r["style"] for r in refs)
    assert "deletion is not advised" in finding["message"]


def test_layer_names_are_case_insensitive(drawing):
    def build(doc):
        rectangle(doc, layer="CUT")
        doc.modelspace().add_line((10, 0), (0, 0), dxfattribs={"layer": "cut"})
    assert "DUP001" in rules(analyze(drawing(build)))


def test_cross_layer_duplicates_not_claimed_as_same_layer_duplicate(drawing):
    def build(doc):
        rectangle(doc, layer="CUT")
        rectangle(doc, layer="ETCH")
    report = analyze(drawing(build))
    assert "DUP001" not in rules(report)
    assert "LAYER001" in rules(report)
    assert len(report["summary"]["layers"]) == 2


def test_mismatched_layers_do_not_close_a_chain(drawing):
    def build(doc):
        rectangle(doc, layer="CUT")
        line = list(doc.modelspace())[-1]
        line.dxf.layer = "ETCH"
    assert "TOPO001" in rules(analyze(drawing(build)))


def test_near_duplicate_coordinates_are_not_rounded_to_exact_duplicate(drawing):
    def build(doc):
        rectangle(doc)
        doc.modelspace().add_line((0, 0.1), (10, 0.1))
    assert "DUP001" not in rules(analyze(drawing(build)))


@pytest.mark.parametrize("unit", [0, None])
def test_unitless_or_missing_stays_incomplete_even_with_expected_unit(drawing, unit):
    path = drawing(rectangle, unit=unit or 0)
    if unit is None:
        doc = ezdxf.readfile(path)
        del doc.header["$INSUNITS"]
        doc.saveas(path)
    report = analyze(path, expected_unit="mm")
    assert report["status"] == "incomplete"
    assert "UNIT001" in rules(report)
    assert report["units"]["scaled_or_inferred"] is False


def test_expected_unit_mismatch_does_not_scale_or_modify(drawing):
    path = drawing(rectangle)
    before = path.read_bytes()
    report = analyze(path, expected_unit="in")
    assert report["status"] == "issues_found"
    assert "UNIT002" in rules(report)
    assert report["units"]["code"] == 4
    assert path.read_bytes() == before


def test_lunits_and_measurement_are_not_used_as_length_units(drawing):
    def build(doc):
        rectangle(doc)
        doc.header["$LUNITS"] = 4
        doc.header["$MEASUREMENT"] = 0
    report = analyze(drawing(build), expected_unit="mm")
    assert report["status"] == "limited_checks_clear"
    assert report["units"]["code"] == 4


@pytest.mark.parametrize("kind", ["ARC", "CIRCLE", "TEXT", "HATCH", "POLYLINE", "SPLINE"])
def test_unsupported_entities_block_clear_result_even_with_valid_rectangle(drawing, kind):
    def build(doc):
        rectangle(doc)
        msp = doc.modelspace()
        if kind == "ARC": msp.add_arc((20, 20), 5, 0, 90)
        elif kind == "CIRCLE": msp.add_circle((20, 20), 5)
        elif kind == "TEXT": msp.add_text("annotation")
        elif kind == "HATCH": msp.add_hatch()
        elif kind == "POLYLINE": msp.add_polyline2d([(0, 0), (1, 0)])
        else: msp.add_spline([(0, 0), (1, 1), (2, 0)])
    report = analyze(drawing(build))
    assert report["status"] == "incomplete"
    assert "SCOPE001" in rules(report)
    assert report["summary"]["unsupported_entities"] == 1


@pytest.mark.parametrize("closed,bulge_at", [(True, 0), (True, -1), (False, -1)])
def test_any_bulge_including_last_or_unused_vertex_is_unsupported(drawing, closed, bulge_at):
    points = [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]]
    points[bulge_at][2] = 0.5
    report = analyze(drawing(lambda d: d.modelspace().add_lwpolyline(points, format="xyb", close=closed)))
    assert report["status"] == "incomplete"
    assert "SCOPE003" in rules(report)
    assert report["summary"]["extracted_segments"] == 0


@pytest.mark.parametrize("kind,attributes", [
    ("LINE", {"extrusion": (0, 0, -1)}),
    ("LINE", {"thickness": 0.01}),
    ("LWPOLYLINE", {"extrusion": (0, 1, 0)}),
    ("LWPOLYLINE", {"elevation": 1e-12}),
    ("LWPOLYLINE", {"thickness": 0.01}),
])
def test_ocs_and_nonzero_attributes_are_never_flattened(drawing, kind, attributes):
    def build(doc):
        if kind == "LINE": doc.modelspace().add_line((0, 0), (10, 0), dxfattribs=attributes)
        else: doc.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 10)], close=True, dxfattribs=attributes)
    report = analyze(drawing(build))
    assert report["status"] == "incomplete"
    assert "SCOPE002" in rules(report)


def test_even_tiny_line_z_offset_blocks_support(drawing):
    report = analyze(drawing(lambda d: d.modelspace().add_line((0, 0, 1e-12), (10, 0, 1e-12))))
    assert report["status"] == "incomplete"
    assert "SCOPE002" in rules(report)


@pytest.mark.parametrize("attributes", [{"const_width": 1}, {}])
def test_polyline_widths_are_unsupported(drawing, attributes):
    points = [(0, 0, 1, 1), (10, 0, 0, 0), (10, 10, 0, 0)]
    report = analyze(drawing(lambda d: d.modelspace().add_lwpolyline(points, format="xyse", close=True, dxfattribs=attributes)))
    assert report["status"] == "incomplete"
    assert "SCOPE004" in rules(report)


@pytest.mark.parametrize("insert,empty", [(True, False), (False, False), (False, True)])
def test_blocks_including_unused_and_empty_are_incomplete(drawing, insert, empty):
    def build(doc):
        rectangle(doc)
        block = doc.blocks.new("PART")
        if not empty: block.add_line((0, 0), (10, 0))
        if insert: doc.modelspace().add_blockref("PART", (100, 100))
    report = analyze(drawing(build))
    assert report["status"] == "incomplete"
    assert "SCOPE005" in rules(report)


def test_paperspace_content_blocks_complete_result(drawing):
    def build(doc):
        rectangle(doc)
        doc.layout().add_line((0, 0), (1, 0))
    report = analyze(drawing(build))
    assert report["status"] == "incomplete"
    assert "SCOPE005" in rules(report)


@pytest.mark.parametrize("gap,warn", [(5e-7, True), (1e-4, False)])
def test_gap_tolerance_has_explicit_findings(drawing, gap, warn):
    def build(doc):
        rectangle(doc)
        list(doc.modelspace())[-1].dxf.end = (gap, 0, 0)
    report = analyze(drawing(build))
    assert report["status"] == "issues_found"
    assert ("TOPO003" in rules(report)) is warn
    assert ("TOPO001" in rules(report)) is not warn


def test_proximity_works_across_bucket_boundary(drawing):
    def build(doc):
        rectangle(doc)
        list(doc.modelspace())[0].dxf.start = (0.99e-6, 0, 0)
        list(doc.modelspace())[-1].dxf.end = (1.01e-6, 0, 0)
    assert "TOPO003" in rules(analyze(drawing(build)))


def test_transitive_tolerance_chain_is_incomplete_not_silently_closed(drawing):
    def build(doc):
        for i in range(3):
            doc.modelspace().add_line((i * 0.75e-6, 0), (i * 5, 10))
    report = analyze(drawing(build))
    assert report["status"] == "incomplete"
    assert "TOPO004" in rules(report)
    assert report["summary"]["layers"][0]["status"] == "incomplete"


def test_near_independent_contours_cannot_silently_become_one(drawing):
    def build(doc):
        rectangle(doc)
        rectangle(doc, shift=10 + 0.5e-6)
    report = analyze(drawing(build))
    assert report["status"] == "issues_found"
    assert {"TOPO002", "TOPO003"} <= rules(report)


def test_branch_node_is_reported(drawing):
    def build(doc):
        rectangle(doc)
        doc.modelspace().add_line((0, 0), (-5, 0))
    assert "TOPO002" in rules(analyze(drawing(build)))


@pytest.mark.parametrize("length", [0, 1e-7])
def test_degenerate_segments_are_issues(drawing, length):
    def build(doc):
        rectangle(doc)
        doc.modelspace().add_line((20, 20), (20 + length, 20))
    report = analyze(drawing(build))
    assert "GEOM002" in rules(report)
    assert report["summary"]["unique_nondegenerate_segments"] == 4


def test_empty_drawing_is_not_clear(drawing):
    report = analyze(drawing())
    assert report["status"] == "issues_found"
    assert "GEOM003" in rules(report)


def test_nonfinite_coordinates_are_blockers(drawing):
    report = analyze(drawing(lambda d: d.modelspace().add_line((float("nan"), 0), (10, 0))))
    assert report["status"] == "incomplete"
    assert "GEOM001" in rules(report)


def test_bowtie_crossing_is_detected_without_manufacturing_approval(drawing):
    points = [(0, 0), (10, 10), (0, 10), (10, 0)]
    report = analyze(drawing(lambda d: d.modelspace().add_lwpolyline(points, close=True)))
    assert report["status"] == "issues_found"
    assert "INTER001" in rules(report)
    assert report["manual_review_required"] is True and report["gate_eligible"] is False
    assert "not a complete manufacturability" in report["disclaimer"]


@pytest.mark.parametrize("second_loop,rule", [
    ([(5, -5), (15, -5), (15, 5), (5, 5)], "INTER001"),
    ([(5, 0), (6, 2), (4, 2)], "INTER002"),
])
def test_independent_review_crossing_and_interior_contact_are_now_detected(drawing, second_loop, rule):
    def build(doc):
        rectangle(doc)
        doc.modelspace().add_lwpolyline(second_loop, close=True)
    report = analyze(drawing(build))
    assert report["status"] == "issues_found"
    assert rule in rules(report)
    assert report["manual_review_required"] is True
    assert report["gate_eligible"] is False
    assert report["summary"]["segment_intersections"]["status"] == "checked"


@pytest.mark.parametrize("limit", ["MAX_FILE_BYTES", "MAX_SEGMENTS", "MAX_ENTITIES", "MAX_COMPARISONS"])
def test_resource_limits_never_return_clear(drawing, monkeypatch, limit):
    def build(doc):
        rectangle(doc)
        list(doc.modelspace())[-1].dxf.end = (0.5e-6, 0, 0)
    path = drawing(build)
    monkeypatch.setattr(core, limit, 1)
    assert analyze(path)["status"] == "incomplete"
    assert "SCOPE007" in rules(analyze(path))


def test_huge_coordinate_tiny_tolerance_is_incomplete_not_crash(drawing):
    report = analyze(drawing(lambda d: d.modelspace().add_line((1e300, 0), (0, 1e300))), tolerance=1e-300)
    assert report["status"] == "incomplete"
    assert "SCOPE007" in rules(report)


def test_external_input_change_during_read_is_detected(drawing, monkeypatch):
    path = drawing(rectangle)
    original_read = core.ezdxf.readfile
    def change_after_read(*args, **kwargs):
        doc = original_read(*args, **kwargs)
        path.write_bytes(path.read_bytes() + b"\n")
        return doc
    monkeypatch.setattr(core.ezdxf, "readfile", change_after_read)
    report = analyze(path)
    assert report["status"] == "incomplete"
    assert report["input"]["unchanged_during_analysis"] is False
    assert "FILE002" in rules(report)


def test_corrupt_and_missing_files_are_unreadable(tmp_path):
    path = tmp_path / "bad.dxf"
    path.write_text("this is not DXF", encoding="utf-8")
    for file in (path, tmp_path / "missing.dxf"):
        report = analyze(file)
        assert report["status"] == "unreadable"
        assert report["manual_review_required"] is True
        assert report["gate_eligible"] is False
        assert "FILE001" in rules(report)


def test_invalid_options_fail_before_analysis(tmp_path):
    for tolerance in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            analyze(tmp_path / "missing", tolerance=tolerance)
    with pytest.raises(ValueError):
        analyze(tmp_path / "missing", expected_unit="guess")


def test_report_is_repeatable_without_timestamps(drawing):
    path = drawing(rectangle)
    assert analyze(path) == analyze(path)


def test_real_default_comparison_budget_bounds_dense_endpoint_case(drawing):
    def build(doc):
        for i in range(1200):
            doc.modelspace().add_line((i * 0.5e-6 / 1200, 0), (10, 0))
    report = analyze(drawing(build))
    assert report["status"] == "incomplete"
    assert "SCOPE007" in rules(report)


def test_large_polyline_is_rejected_before_segment_expansion(drawing):
    report = analyze(drawing(lambda d: d.modelspace().add_lwpolyline([(i, i % 2) for i in range(10002)])))
    assert report["status"] == "incomplete"
    assert "SCOPE007" in rules(report)
    assert report["summary"]["extracted_segments"] == 0


def test_fifo_is_rejected_without_blocking_on_read(tmp_path):
    import os
    path = tmp_path / "pipe.dxf"
    os.mkfifo(path)
    assert analyze(path)["status"] == "unreadable"


def test_unknown_unit_code_cannot_be_clear(drawing):
    def build(doc):
        rectangle(doc)
        doc.header["$INSUNITS"] = 99
    report = analyze(drawing(build))
    assert report["status"] == "incomplete"
    assert "UNIT001" in rules(report)


def test_truncated_dxf_is_unreadable(drawing):
    path = drawing(rectangle)
    data = path.read_bytes()
    path.write_bytes(data[:len(data) // 2])
    assert analyze(path)["status"] == "unreadable"


@pytest.mark.parametrize("name,status", [
    ("rectangle_lines", "limited_checks_clear"),
    ("rectangle_polyline", "limited_checks_clear"),
    ("duplicate_reverse", "issues_found"),
    ("open_chain", "issues_found"),
    ("tolerance_gap", "issues_found"),
    ("unitless", "incomplete"),
    ("unsupported_arc", "incomplete"),
    ("bulged_polyline", "incomplete"),
    ("block_insert", "incomplete"),
    ("non_xy_line", "incomplete"),
    ("self_crossing", "issues_found"),
    ("intersecting_rectangles", "issues_found"),
    ("interior_endpoint_contact", "issues_found"),
    ("collinear_overlap", "issues_found"),
    ("parallel_disjoint", "issues_found"),
])
def test_included_fixture_statuses_and_saved_report_source_hash(name, status):
    import json
    root = Path(__file__).parents[1]
    report = analyze(root / "fixtures" / f"{name}.dxf", expected_unit="mm")
    saved = json.loads((root / "reports" / f"{name}.json").read_text())
    assert report["status"] == status
    assert report["input"]["sha256"] == saved["input"]["sha256"]
    assert report["findings"] == saved["findings"]


def test_parser_reads_only_the_report_hashed_snapshot(drawing, monkeypatch, tmp_path):
    import hashlib
    path = drawing(lambda doc: doc.modelspace().add_line((0, 0), (10, 0)))
    original = path.read_bytes()
    alternate = ezdxf.new('R2010')
    alternate.units = 4
    rectangle(alternate)
    alternate_path = tmp_path / 'alternate.dxf'
    alternate.saveas(alternate_path)
    alternate_bytes = alternate_path.read_bytes()
    original_read = core.ezdxf.readfile
    parser_paths = []
    def transient_change(snapshot, *args, **kwargs):
        parser_paths.append(Path(snapshot))
        assert Path(snapshot) != path
        assert Path(snapshot).read_bytes() == original
        path.write_bytes(alternate_bytes)
        try:
            return original_read(snapshot, *args, **kwargs)
        finally:
            path.write_bytes(original)
    monkeypatch.setattr(core.ezdxf, 'readfile', transient_change)
    report = analyze(path)
    assert report['status'] == 'issues_found'
    assert 'TOPO001' in rules(report)
    assert report['input']['sha256'] == hashlib.sha256(original).hexdigest()
    assert report['input']['unchanged_during_analysis'] is True
    assert path.read_bytes() == original
    assert all(not p.exists() for p in parser_paths)


def test_unreadable_parser_reports_are_repeatable_without_temp_path(tmp_path):
    path = tmp_path / 'not a drawing.dxf'
    path.write_bytes(b'not a DXF')
    first = analyze(path)
    second = analyze(path)
    assert first == second
    assert first['status'] == 'unreadable'
    assert 'dxf-preflight-snapshot-' not in first['findings'][0]['details']['reason']
    assert str(path) in first['findings'][0]['details']['reason']
