"""Original analytic oracles, synthetic DXFs and fail-closed curve regressions."""

from copy import deepcopy
from fractions import Fraction
import json
import math
import random

import ezdxf
import pytest

from dxf_preflight import analyze, core, supervisor
from dxf_preflight.cli import main, render_text
from dxf_preflight.curves import CurveMeasurementError, measure_curve


@pytest.fixture
def drawing(tmp_path):
    def save(build):
        doc = ezdxf.new('R2010')
        doc.units = 4
        build(doc)
        path = tmp_path / 'original_curve.dxf'
        doc.saveas(path)
        return path
    return save


def assert_conservative(report):
    supervisor.VALIDATOR.validate(report)
    assert report['status'] == 'incomplete'
    assert report['coverage_complete_for_declared_subset'] is False
    assert report['read_only'] is True
    assert report['manual_review_required'] is True
    assert report['gate_eligible'] is False
    assert 'SCOPE001' in {f['rule_id'] for f in report['findings']}


def test_translated_circle_analytic_length_and_bounds(drawing):
    path = drawing(lambda d: d.modelspace().add_circle((13, -7), 5, dxfattribs={'layer': 'ETCH', 'color': 1}))
    before = path.read_bytes()
    report = analyze(path, expected_unit='mm')
    assert_conservative(report)
    summary = report['summary']['curve_measurements']
    assert summary['status'] == 'checked'
    assert summary['scanned_curve_entities'] == summary['measured_entities'] == 1
    assert summary['skipped_entities'] == 0
    curve = summary['measurements'][0]
    assert curve['center'] == [13, -7]
    assert curve['radius'] == 5
    assert curve['length'] == pytest.approx(10 * math.pi)
    assert curve['bounds'] == {'minimum': [8, -12], 'maximum': [18, -2]}
    assert curve['style']['entity_color'] == 1
    assert curve['layer'] == 'ETCH' and curve['handle']
    assert curve['operation_inferred'] is False
    assert curve['bounds_are_approximate'] is curve['length_is_approximate'] is True
    assert summary['contour_checks'] == 'not_run'
    assert report['summary']['extracted_segments'] == 0
    assert report['summary']['layers'] == []
    assert path.read_bytes() == before
    assert analyze(path, expected_unit='mm') == report


@pytest.mark.parametrize('start,end,sweep,low,high,first,last', [
    (0, 90, 90, [10, -3], [12, -1], [12, -3], [10, -1]),
    (90, 180, 90, [8, -3], [10, -1], [10, -1], [8, -3]),
    (180, 270, 90, [8, -5], [10, -3], [8, -3], [10, -5]),
    (270, 0, 90, [10, -5], [12, -3], [10, -5], [12, -3]),
    (0, 180, 180, [8, -3], [12, -1], [12, -3], [8, -3]),
    (90, 0, 270, [8, -5], [12, -1], [10, -1], [12, -3]),
    (-90, 0, 90, [10, -5], [12, -3], [10, -5], [12, -3]),
    (720, 810, 90, [10, -3], [12, -1], [12, -3], [10, -1]),
])
def test_arc_quadrants_major_wrap_negative_and_normalized_oracles(start, end, sweep, low, high, first, last):
    curve = measure_curve('ARC', (10, -3), 2, start, end)
    assert curve['counterclockwise_sweep_degrees'] == sweep
    assert curve['length'] == pytest.approx(2 * math.pi * sweep / 180)
    assert curve['bounds'] == {'minimum': low, 'maximum': high}
    assert curve['start'] == first and curve['end'] == last
    assert curve['start_angle_degrees'] == start and curve['end_angle_degrees'] == end


@pytest.mark.parametrize('start,end,low,high', [
    (30, 60, [1, 1], [math.sqrt(3), math.sqrt(3)]),
    (45, 135, [-math.sqrt(2), math.sqrt(2)], [math.sqrt(2), 2]),
    (315, 45, [math.sqrt(2), -math.sqrt(2)], [2, math.sqrt(2)]),
    (45, 315, [-2, -2], [math.sqrt(2), 2]),
])
def test_noncardinal_arc_bounds_include_only_reached_extrema(start, end, low, high):
    curve = measure_curve('ARC', (0, 0), 2, start, end)
    assert curve['bounds']['minimum'] == pytest.approx(low)
    assert curve['bounds']['maximum'] == pytest.approx(high)


def test_broad_deterministic_angles_against_sampled_envelope():
    # Independent dense sampling catches omitted interior cardinal extrema.
    # Sampling is only a test oracle, never used by production analysis.
    rng = random.Random(4012)
    for _ in range(150):
        start, end = rng.uniform(-1000, 1000), rng.uniform(-1000, 1000)
        radius = rng.uniform(0.5, 100)
        center = (rng.uniform(-100, 100), rng.uniform(-100, 100))
        curve = measure_curve('ARC', center, radius, start, end)
        sweep = (end - start) % 360
        assert curve['counterclockwise_sweep_degrees'] == pytest.approx(sweep)
        assert curve['length'] == pytest.approx(radius * math.pi * sweep / 180)
        for i in range(1001):
            theta = (start + sweep * i / 1000) * math.pi / 180
            xy = (center[0] + radius * math.cos(theta), center[1] + radius * math.sin(theta))
            for axis, value in enumerate(xy):
                assert curve['bounds']['minimum'][axis] - 1e-10 <= value <= curve['bounds']['maximum'][axis] + 1e-10


@pytest.mark.parametrize('kind,center,radius,start,end,rule', [
    ('CIRCLE', (0, 0), 0, None, None, 'GEOM002'),
    ('CIRCLE', (0, 0), -1, None, None, 'GEOM002'),
    ('CIRCLE', (math.nan, 0), 1, None, None, 'GEOM001'),
    ('CIRCLE', (0, 0), math.inf, None, None, 'GEOM001'),
    ('ARC', (0, 0), 1, math.nan, 90, 'GEOM001'),
    ('ARC', (0, 0), 1, 0, math.inf, 'GEOM001'),
    ('ARC', (0, 0), 1, 0, 0, 'GEOM002'),
    ('ARC', (0, 0), 1, 0, 360, 'GEOM002'),
    ('ARC', (0, 0), 1, -90, 270, 'GEOM002'),
    ('CIRCLE', (1e308, 0), 1e308, None, None, 'SCOPE007'),
    ('CIRCLE', (0, 0), 1e308, None, None, 'SCOPE007'),
    ('CIRCLE', (1e20, 0), 1, None, None, 'SCOPE007'),
    ('ARC', (0, 0), 1, 0, math.nextafter(0, 1), 'SCOPE007'),
    ('ARC', (0, 0), 1, -math.nextafter(0, 1), 90, 'SCOPE007'),
    ('ARC', (1e5, 1e5), 1, 45, math.nextafter(45, math.inf), 'SCOPE007'),
])
def test_nonfinite_degenerate_overflow_underflow_and_collapse_are_not_measurements(kind, center, radius, start, end, rule):
    with pytest.raises(CurveMeasurementError) as exc:
        measure_curve(kind, center, radius, start, end)
    assert exc.value.rule == rule


@pytest.mark.parametrize('kind', ['CIRCLE', 'ARC'])
@pytest.mark.parametrize('center,attributes,rule', [
    ((0, 0, 1e-12), {}, 'SCOPE002'),
    ((0, 0), {'extrusion': (0, 0, -1)}, 'SCOPE002'),
    ((0, 0), {'extrusion': (0, 1, 0)}, 'SCOPE002'),
    ((0, 0), {'thickness': 1e-12}, 'SCOPE002'),
    ((math.nan, 0), {}, 'GEOM001'),
    ((0, 0), {'thickness': math.inf}, 'GEOM001'),
])
def test_dxf_non_xy_ocs_thickness_and_nonfinite_rejected(drawing, kind, center, attributes, rule):
    def build(doc):
        msp = doc.modelspace()
        if kind == 'ARC': msp.add_arc(center, 5, 0, 90, dxfattribs=attributes)
        else: msp.add_circle(center, 5, dxfattribs=attributes)
    path = drawing(build)
    before = path.read_bytes()
    report = analyze(path)
    assert_conservative(report)
    assert rule in {f['rule_id'] for f in report['findings']}
    summary = report['summary']['curve_measurements']
    assert summary['status'] == 'unknown'
    assert summary['measurements'] == []
    assert summary['skipped_entities'] == summary['scanned_curve_entities'] == 1
    assert path.read_bytes() == before
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize('kind', ['CIRCLE', 'ARC'])
@pytest.mark.parametrize('radius', [0, -1, math.nan, math.inf])
def test_bad_dxf_radius_is_never_measured(drawing, kind, radius):
    def build(doc):
        if kind == 'ARC': doc.modelspace().add_arc((0, 0), radius, 0, 90)
        else: doc.modelspace().add_circle((0, 0), radius)
    report = analyze(drawing(build))
    assert_conservative(report)
    assert report['summary']['curve_measurements']['measured_entities'] == 0
    assert report['summary']['curve_measurements']['skipped_entities'] == 1
    json.dumps(report, allow_nan=False)


def test_curves_never_close_line_graph_or_establish_curve_intersections(drawing):
    def build(doc):
        doc.modelspace().add_line((5, 0), (0, 5))
        doc.modelspace().add_arc((0, 0), 5, 0, 90)
        doc.modelspace().add_circle((0, 0), 5)
        doc.modelspace().add_circle((0, 0), 5)
    report = analyze(drawing(build))
    assert_conservative(report)
    assert report['summary']['curve_measurements']['measured_entities'] == 3
    layer = report['summary']['layers'][0]
    assert layer['open_endpoint_count'] == 2
    assert layer['degree_two_cycle_components'] == 0
    assert report['summary']['extracted_segments'] == 1
    assert 'DUP001' not in {f['rule_id'] for f in report['findings']}
    assert not any(f['rule_id'].startswith('INTER') for f in report['findings'])


def test_blocks_and_paperspace_curves_are_not_measured(drawing):
    def build(doc):
        doc.blocks.new('CURVES').add_circle((0, 0), 5)
        doc.modelspace().add_blockref('CURVES', (100, 0))
        doc.layout().add_arc((0, 0), 5, 0, 90)
    report = analyze(drawing(build))
    assert report['status'] == 'incomplete'
    assert report['summary']['curve_measurements']['scanned_curve_entities'] == 0
    assert report['summary']['curve_measurements']['measurements'] == []
    assert 'SCOPE005' in {f['rule_id'] for f in report['findings']}


def test_measurement_budget_counts_skipped_and_keeps_known_prefix(drawing, monkeypatch):
    monkeypatch.setattr(core, 'MAX_CURVE_MEASUREMENTS', 2)
    def build(doc):
        for i in range(5): doc.modelspace().add_circle((10 * i, 0), 2)
    report = analyze(drawing(build))
    assert_conservative(report)
    summary = report['summary']['curve_measurements']
    assert summary['status'] == 'unknown'
    assert summary['scanned_curve_entities'] == 5
    assert summary['measured_entities'] == len(summary['measurements']) == 2
    assert summary['skipped_entities'] == 3
    assert len([f for f in report['findings'] if f['rule_id'] == 'SCOPE007']) == 1
    supervisor._check_worker_result(deepcopy(report))


def test_entity_scan_truncation_never_reports_complete_curve_population(drawing, monkeypatch):
    monkeypatch.setattr(core, 'MAX_ENTITIES', 1)
    path = drawing(lambda d: [d.modelspace().add_circle((10 * i, 0), 2) for i in range(3)])
    report = analyze(path)
    assert_conservative(report)
    summary = report['summary']['curve_measurements']
    assert summary['status'] == 'unknown'
    assert summary['scanned_curve_entities'] == summary['measured_entities'] == 1
    assert report['checks']['scope'] == 'unknown'


def test_attribute_failure_has_no_partial_measurement(drawing, monkeypatch):
    def reject_style(*args): raise ValueError('controlled bad style')
    monkeypatch.setattr(core, '_entity_style', reject_style)
    report = analyze(drawing(lambda d: d.modelspace().add_circle((0, 0), 2)))
    summary = report['summary']['curve_measurements']
    assert summary['measured_entities'] == 0 and summary['skipped_entities'] == 1
    assert summary['status'] == 'unknown'
    assert 'SCOPE008' in {f['rule_id'] for f in report['findings']}
    assert summary['measurements'] == []


def test_units_mismatch_never_scales_curve_measurements(drawing):
    path = drawing(lambda d: d.modelspace().add_circle((0, 0), 25.4))
    report = analyze(path, expected_unit='in')
    assert_conservative(report)
    assert report['summary']['curve_measurements']['measurements'][0]['radius'] == 25.4
    assert report['summary']['curve_measurements']['unit'] == 'drawing units'
    assert report['units']['scaled_or_inferred'] is False
    assert 'UNIT002' in {f['rule_id'] for f in report['findings']}


def test_unreadable_and_worker_failures_have_no_fabricated_curve_measurements(tmp_path, monkeypatch):
    report = analyze(tmp_path / 'missing.dxf')
    assert report['summary']['curve_measurements']['status'] == 'not_run'
    monkeypatch.setattr(supervisor, '_worker_command', lambda: ['/definitely/not/a/worker'])
    report = supervisor.analyze_supervised(tmp_path / 'missing.dxf', tolerance=1e-6, expected_unit=None, timeout=1)
    assert report['status'] == 'incomplete'
    summary = report['summary']['curve_measurements']
    assert summary['status'] == 'unknown' and summary['measurements'] == []


@pytest.mark.parametrize('mutation', ['count', 'skips', 'status', 'missing_state', 'missing_blocker', 'inverted_bounds', 'contour_checked', 'exact_length'])
def test_schema_and_worker_reject_contradictory_curve_results(drawing, mutation):
    report = analyze(drawing(lambda d: d.modelspace().add_circle((0, 0), 2)))
    curves = report['summary']['curve_measurements']
    if mutation == 'count': curves['measured_entities'] = 5
    elif mutation == 'skips': curves['skipped_entities'] = 1
    elif mutation == 'status': curves['status'] = 'not_run'
    elif mutation == 'missing_state': del report['summary']['curve_measurements']
    elif mutation == 'missing_blocker':
        report['findings'] = [f for f in report['findings'] if f['rule_id'] != 'SCOPE001']
        core._finish(report)
    elif mutation == 'inverted_bounds': curves['measurements'][0]['bounds']['minimum'][0] = 100
    elif mutation == 'contour_checked': curves['contour_checks'] = 'checked'
    elif mutation == 'exact_length': curves['measurements'][0]['length_is_approximate'] = False
    with pytest.raises(ValueError): supervisor._check_worker_result(report)


def test_text_and_supervised_cli_show_measurements_without_claiming_curve_support(drawing, capsys):
    path = drawing(lambda d: d.modelspace().add_arc((10, 20), 5, 270, 90))
    before = path.read_bytes()
    assert main([str(path), '--format', 'json']) == 2
    report = json.loads(capsys.readouterr().out)
    assert_conservative(report)
    assert report['execution']['mode'] == 'subprocess'
    text = render_text(report)
    assert 'approximate length' in text and 'Approximate XY bounds' in text
    assert 'all curve contour checks NOT RUN' in text
    assert 'Counterclockwise sweep: 180.0 degrees' in text
    assert 'MANUAL REVIEW REQUIRED' in text
    assert 'measurement-only reporting does not check duplicates, intersections or closure' in text
    assert path.read_bytes() == before


def test_text_caps_curve_display_but_json_retains_all_measurements(drawing):
    path = drawing(lambda d: [d.modelspace().add_circle((i * 10, 0), 2) for i in range(10)])
    report = analyze(path)
    assert len(report['summary']['curve_measurements']['measurements']) == 10
    text = render_text(report)
    assert text.count('approximate length') == 8
    assert 'Showing 8 of 10 measured curves' in text


@pytest.mark.parametrize('kind,attribute', [('CIRCLE', 'center'), ('CIRCLE', 'radius'), ('ARC', 'center'), ('ARC', 'radius'), ('ARC', 'start_angle'), ('ARC', 'end_angle')])
def test_missing_required_curve_attributes_never_inherit_parser_defaults(drawing, monkeypatch, kind, attribute):
    def build(doc):
        if kind == 'ARC': doc.modelspace().add_arc((10, 20), 5, 30, 90)
        else: doc.modelspace().add_circle((10, 20), 5)
    path = drawing(build)
    original_reader = ezdxf.readfile
    def missing_attribute(*args, **kwargs):
        doc = original_reader(*args, **kwargs)
        entity = next(iter(doc.modelspace()))
        entity.dxf.discard(attribute)
        return doc
    monkeypatch.setattr(core.ezdxf, 'readfile', missing_attribute)
    report = analyze(path)
    assert_conservative(report)
    summary = report['summary']['curve_measurements']
    assert summary['status'] == 'unknown' and summary['measurements'] == []
    assert summary['measured_entities'] == 0 and summary['skipped_entities'] == 1
    finding = next(f for f in report['findings'] if f['rule_id'] == 'SCOPE008')
    assert finding['details']['missing_attributes'] == [attribute]


@pytest.mark.parametrize('kind,group', [('CIRCLE', 10), ('CIRCLE', 20), ('CIRCLE', 30), ('CIRCLE', 40), ('ARC', 10), ('ARC', 20), ('ARC', 30), ('ARC', 40), ('ARC', 50), ('ARC', 51)])
def test_raw_missing_coordinate_or_attribute_tags_never_fabricate_measurement(drawing, kind, group):
    def build(doc):
        if kind == 'ARC': doc.modelspace().add_arc((2, 3), 5, 30, 90)
        else: doc.modelspace().add_circle((2, 3), 5)
    path = drawing(build)
    lines = path.read_text().splitlines()
    entity_value = lines.index(kind)
    position = entity_value + 1
    while position < len(lines) and lines[position].strip() != '0':
        if int(lines[position]) == group:
            del lines[position:position + 2]
            break
        position += 2
    else: raise AssertionError('Expected synthetic entity tag not found')
    path.write_text('\n'.join(lines) + '\n')
    before = path.read_bytes()
    report = analyze(path)
    supervisor.VALIDATOR.validate(report)
    summary = report['summary']['curve_measurements']
    if group == 20:
        assert report['status'] == 'unreadable'
        assert summary['status'] == 'not_run' and summary['measurements'] == []
    elif group == 30:
        assert_conservative(report)
        assert summary['status'] == 'checked' and summary['measured_entities'] == 1
        assert summary['measurements'][0]['center'] == [2, 3]
    else:
        assert_conservative(report)
        assert summary['status'] == 'unknown' and summary['skipped_entities'] == 1
        assert summary['measured_entities'] == 0 and summary['measurements'] == []
        assert 'SCOPE008' in {f['rule_id'] for f in report['findings']}
    assert path.read_bytes() == before


@pytest.mark.parametrize('start,end', [(1e308, 90.0), (-1e308, 1e308)])
def test_extreme_finite_angles_normalize_without_subtraction_overflow(start, end):
    curve = measure_curve('ARC', (0, 0), 2, start, end)
    expected_start = Fraction(start) % 360
    expected_end = Fraction(end) % 360
    expected_sweep = (expected_end - expected_start) % 360
    assert curve['normalized_start_angle_degrees'] == float(expected_start)
    assert curve['normalized_end_angle_degrees'] == float(expected_end)
    assert curve['counterclockwise_sweep_degrees'] == float(expected_sweep)
    assert curve['length'] == pytest.approx(2 * math.pi * float(expected_sweep) / 180)
