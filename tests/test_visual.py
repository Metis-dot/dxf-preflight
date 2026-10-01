"""Original offline-preview tests; synthetic geometry is never CAM validation."""

from copy import deepcopy
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import ezdxf
import pytest

from dxf_preflight import analyze, core, supervisor, visual
from dxf_preflight.cli import main, render_text

ROOT = Path(__file__).parents[1]
PYTHON = sys.executable


def bundle(path):
    payload = []
    report = core._analyze(path, expected_unit='mm', _on_geometry=payload.append)
    return report, payload[0] if payload else None


def synthetic(segments):
    report = analyze(ROOT / 'fixtures/rectangle_lines.dxf')
    report['summary']['extracted_segments'] = len(segments)
    return report, visual.capture_geometry(segments, report, scan_complete=True)


def svg_tree(html):
    start, end = html.find('<svg '), html.find('</svg>')
    return ET.fromstring(html[start:end + 6]) if start >= 0 else None


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.attrs = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)


@pytest.mark.parametrize('path', sorted((ROOT / 'fixtures').glob('*.dxf')), ids=lambda p: p.stem)
def test_fixture_preview_reuses_analysis_without_changing_report(path):
    report, geometry = bundle(path)
    assert report == analyze(path, expected_unit='mm')
    before = deepcopy((report, geometry))
    html = visual.render_html(report, geometry)
    assert before == (report, geometry)
    assert 'MANUAL REVIEW REQUIRED' in html and 'gate_eligible: false' in html
    assert report['input']['sha256'] in html
    assert report['status'] in html and report['schema_version'] == '1.1'
    assert 'unsupported geometry is never drawn' in html
    if geometry['segments']:
        assert svg_tree(html) is not None
    if report['summary']['unsupported_entities']:
        assert report['status'] == 'incomplete'
        assert 'No plotted location; use the CAD locators below' in html


def test_geometry_capture_is_the_same_snapshot_and_does_not_add_source_reads(tmp_path, monkeypatch):
    path = tmp_path / 'snapshot.dxf'
    path.write_bytes((ROOT / 'fixtures/open_chain.dxf').read_bytes())
    reads, parses = [], []
    original_open, original_readfile = Path.open, core.ezdxf.readfile

    def track_open(self, *args, **kwargs):
        if self == path:
            reads.append(args[0] if args else 'r')
        return original_open(self, *args, **kwargs)

    def track_parse(snapshot, **kwargs):
        assert snapshot != path
        parses.append(Path(snapshot).read_bytes())
        return original_readfile(snapshot, **kwargs)

    monkeypatch.setattr(Path, 'open', track_open)
    monkeypatch.setattr(core.ezdxf, 'readfile', track_parse)
    report, geometry = bundle(path)
    assert reads == ['rb', 'rb'] and len(parses) == 1
    assert geometry['sha256'] == report['input']['sha256']
    assert geometry['segments'][0]['start'] == [0.0, 0.0]
    assert report['input']['unchanged_during_analysis'] is True


def test_completed_worker_reports_equal_with_or_without_visual_payload():
    path = ROOT / 'fixtures/open_chain.dxf'
    plain = supervisor.analyze_supervised(path, tolerance=1e-6, expected_unit='mm', timeout=30)
    report, geometry = supervisor.analyze_visual_supervised(path, tolerance=1e-6, expected_unit='mm', timeout=30)
    assert report == plain
    assert 'geometry' not in report and 'visualization' not in report
    assert len(geometry['segments']) == 3


def test_hostile_metadata_is_escaped_and_cannot_become_markup():
    hostile = '</title><script>alert("x")</script><svg onload="bad"> & https://example.invalid/秘密'
    report, geometry = synthetic([core.Segment((0, 0), (10, 0), hostile, hostile, 0)])
    report['input']['path'] = hostile
    report['findings'] = [{'rule_id': 'GEOM002', 'severity': 'error', 'message': hostile,
                           'details': {'entity': {'handle': hostile, 'segment_index': 0, 'layer': hostile}, 'start': [0, 0], 'end': [10, 0]}}]
    html = visual.render_html(report, geometry)
    elements = Elements()
    elements.feed(html)
    assert 'script' not in elements.tags
    assert not any(name.startswith('on') for name, _ in elements.attrs)
    assert '&lt;script&gt;' in html and '秘密' in html
    assert 'default-src &#' not in html  # CSP is a fixed attribute, not user data.
    for name, value in elements.attrs:
        if name in {'href', 'src'}:
            assert name == 'href' and value.startswith('#')
    assert svg_tree(html) is not None


def test_long_locator_names_do_not_create_false_segment_matches():
    name = 'a' * 100_000
    report, geometry = synthetic([core.Segment((0, 0), (10, 0), name, name, 0)])
    report['findings'] = [{'rule_id': 'DUP001', 'severity': 'error', 'message': 'test',
                           'details': {'segments': [{'handle': name, 'segment_index': 0, 'layer': name}]}}]
    html = visual.render_html(report, geometry)
    assert geometry['segments'][0]['locator_shortened'] is True
    assert 'cannot be matched for segment highlights' in html
    assert 'No plotted location' in html
    assert name not in html and len(html) < 15_000
    assert 'shortened' in html


@pytest.mark.parametrize('coords', [
    ((-1e308, -1e308), (1e308, 1e308)),
    ((1e308, 1e308), (math.nextafter(1e308, math.inf), 1e308)),
    ((0.0, 0.0), (5e-324, 5e-324)),
    ((0.0, 1.0), (5e-324, 1.0)),
    ((0.0, 1.0), (1e-309, 1.0)),
    ((-5e-324, 0.0), (5e-324, 0.0)),
    ((0.0, 0.0), (0.0, 0.0)),
    ((0.0, -100.0), (0.0, 100.0)),
    ((-100.0, 0.0), (100.0, 0.0)),
])
def test_finite_extreme_coordinates_produce_finite_bounded_svg(coords):
    report, geometry = synthetic([core.Segment(*coords, '0', 'A', 0)])
    tree = svg_tree(visual.render_html(report, geometry))
    for element in tree.iter():
        for name, value in element.attrib.items():
            if name in {'x', 'y', 'x1', 'x2', 'y1', 'y2', 'cx', 'cy', 'r'}:
                assert math.isfinite(float(value))
                assert -1 <= float(value) <= 820


def test_segment_and_finding_and_marker_budgets_are_explicit_and_do_not_change_status():
    segments = [core.Segment((i, 0), (i, 1), '0', f'{i:X}', 0) for i in range(3_000)]
    report, geometry = synthetic(segments)
    report['findings'] = [{'rule_id': 'TOPO001', 'severity': 'error', 'message': 'many endpoints',
                           'details': {'endpoints': [{'point': [i, j], 'entities': []} for j in range(100)]}}
                          for i in range(1_000)]
    report['status'] = 'issues_found'
    before = deepcopy(report)
    html = visual.render_html(report, geometry)
    assert report == before
    assert len(geometry['segments']) == 2_000
    assert html.count('<article ') == 256
    assert html.count('class="marker"') == 512
    assert 'Drawn 2000 of 3000' in html and 'Showing 256 of 1000' in html
    assert 'Additional findings are omitted' in html and 'Display locators/markers are shortened' in html
    assert len(html) < 1_200_000


@pytest.mark.parametrize('rule,details,label', [
    ('TOPO001', {'endpoints': [{'point': [0, 0], 'entities': []}]}, 'reported endpoint-graph representative'),
    ('TOPO002', {'nodes': [{'point': [0, 0], 'entities': [], 'degree': 3}]}, 'reported endpoint-graph representative'),
    ('TOPO003', {'clusters': [[[0, 0], [0.0000005, 0]]]}, 'reported cluster coordinate sample'),
    ('TOPO004', {'clusters': [[[0, 0], [0.0000005, 0], [0.0000015, 0]]]}, 'reported cluster coordinate sample'),
    ('GEOM002', {'start': [0, 0], 'end': [0, 0]}, 'start:'),
    ('INTER001', {'point': [0, 0], 'point_is_approximate': True}, 'approximate crossing display'),
    ('INTER002', {'contact_points': [[0, 0]]}, 'contact_points:'),
    ('INTER003', {'overlap_endpoints': [[0, 0], [1, 0]]}, 'overlap_endpoints:'),
])
def test_known_locations_have_numbered_links_and_truthful_labels(rule, details, label):
    report, geometry = synthetic([core.Segment((-2, 0), (2, 0), '0', 'A', 0)])
    report['findings'] = [{'rule_id': rule, 'severity': 'error', 'message': 'test', 'details': details}]
    html = visual.render_html(report, geometry)
    assert label in html
    assert 'href="#loc-1"' in html and 'href="#issue-1"' in html
    assert 'id="loc-1"' in html and 'id="issue-1"' in html


def test_unknown_findings_are_kept_without_inventing_xy_location():
    report, geometry = synthetic([core.Segment((0, 0), (10, 0), '0', 'A', 0)])
    report['findings'] = [{'rule_id': 'FUTURE001', 'severity': 'blocker', 'message': 'unknown check', 'details': {'point': [5, 0]}}]
    html = visual.render_html(report, geometry)
    assert 'FUTURE001' in html and 'unknown check' in html
    assert 'No plotted location' in html
    assert 'class="marker"' not in html


@pytest.mark.parametrize('path', ['missing.dxf', 'bad.dxf'])
def test_unreadable_input_has_no_fabricated_geometry(tmp_path, path):
    source = tmp_path / path
    if path == 'bad.dxf':
        source.write_text('not dxf')
    report, geometry = bundle(source)
    assert geometry is None
    html = visual.render_html(report, geometry)
    assert 'unreadable' in html and 'No supported snapshot geometry' in html
    assert svg_tree(html) is None


def test_truncated_extraction_remains_explicitly_incomplete(monkeypatch):
    monkeypatch.setattr(core, 'MAX_ENTITIES', 1)
    report, geometry = bundle(ROOT / 'fixtures/rectangle_lines.dxf')
    html = visual.render_html(report, geometry)
    assert report['status'] == 'incomplete'
    assert geometry['scan_complete'] is False
    assert 'unscanned remainder is unknown' in html


@pytest.mark.parametrize('mutation', ['missing', 'wrong_hash', 'wrong_count', 'wrong_scan', 'extra', 'nan', 'inf', 'bool', 'huge_int', 'bad_index', 'large_index', 'bool_index', 'bad_layer', 'too_many'])
def test_display_transport_rejects_invalid_or_unbounded_payload(mutation):
    report, geometry = bundle(ROOT / 'fixtures/open_chain.dxf')
    if mutation == 'missing': geometry = None
    elif mutation == 'wrong_hash': geometry['sha256'] = 'b' * 64
    elif mutation == 'wrong_count': geometry['extracted_segments'] += 1
    elif mutation == 'wrong_scan': geometry['scan_complete'] = False
    elif mutation == 'extra': geometry['unexpected'] = True
    elif mutation == 'nan': geometry['segments'][0]['start'][0] = float('nan')
    elif mutation == 'inf': geometry['segments'][0]['start'][0] = float('inf')
    elif mutation == 'bool': geometry['segments'][0]['start'][0] = True
    elif mutation == 'huge_int': geometry['segments'][0]['start'][0] = 10 ** 400
    elif mutation == 'bad_index': geometry['segments'][0]['segment_index'] = -1
    elif mutation == 'large_index': geometry['segments'][0]['segment_index'] = 10_001
    elif mutation == 'bool_index': geometry['segments'][0]['segment_index'] = True
    elif mutation == 'bad_layer': geometry['segments'][0]['layer'] = 'x' * 257
    elif mutation == 'too_many': geometry['segments'] *= 2_000
    with pytest.raises(ValueError):
        visual.validate_geometry(geometry, report)


def test_invalid_display_worker_payload_fails_closed_without_geometry(monkeypatch):
    path = ROOT / 'fixtures/open_chain.dxf'
    report, geometry = bundle(path)
    geometry['segments'][0]['start'][0] = 10 ** 400
    records = [json.dumps({'kind': 'snapshot', 'path': str(path), 'sha256': report['input']['sha256']}),
               json.dumps({'kind': 'report', 'report': report, 'geometry': geometry})]
    monkeypatch.setattr(supervisor, '_worker_command', lambda: [PYTHON, '-c', '\n'.join('print(%r)' % row for row in records)])
    result, payload = supervisor.analyze_visual_supervised(path, tolerance=1e-6, expected_unit='mm', timeout=5)
    assert result['status'] == 'incomplete' and payload is None
    assert result['findings'][0]['rule_id'] == 'SCOPE009'


def test_timeout_has_no_display_geometry_and_keeps_original_exit_meaning(tmp_path, capsys):
    html_path = tmp_path / 'timeout.html'
    assert main([str(ROOT / 'fixtures/open_chain.dxf'), '--html-report', str(html_path), '--format', 'json', '--timeout', '0.000001']) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'incomplete'
    assert 'No supported snapshot geometry' in html_path.read_text()


@pytest.mark.parametrize('alias', ['same', 'symlink', 'hardlink'])
@pytest.mark.parametrize('target', ['input', 'json', 'text'])
def test_html_output_cannot_alias_any_input_or_other_report(tmp_path, alias, target):
    source = tmp_path / 'input.dxf'
    source.write_bytes((ROOT / 'fixtures/open_chain.dxf').read_bytes())
    json_path, text_path = tmp_path / 'out.json', tmp_path / 'out.txt'
    json_path.write_text('preserved json')
    text_path.write_text('preserved text')
    chosen = {'input': source, 'json': json_path, 'text': text_path}[target]
    html = chosen if alias == 'same' else tmp_path / 'html.alias'
    if alias == 'symlink': html.symlink_to(chosen)
    elif alias == 'hardlink': os.link(chosen, html)
    before = source.read_bytes()
    with pytest.raises(SystemExit) as caught:
        main([str(source), '--json-report', str(json_path), '--text-report', str(text_path), '--html-report', str(html)])
    assert caught.value.code == 2
    assert source.read_bytes() == before
    assert json_path.read_text() == 'preserved json' and text_path.read_text() == 'preserved text'


def test_three_reports_keep_json_text_stdout_and_status_unchanged(tmp_path, capsys):
    path = ROOT / 'fixtures/open_chain.dxf'
    args = [str(path), '--expected-unit', 'mm', '--format', 'json']
    assert main(args) == 1
    plain = capsys.readouterr().out
    outputs = [tmp_path / name for name in ('out.json', 'out.txt', 'out.html')]
    assert main(args + ['--json-report', str(outputs[0]), '--text-report', str(outputs[1]), '--html-report', str(outputs[2])]) == 1
    assert capsys.readouterr().out == plain
    report = json.loads(plain)
    assert outputs[0].read_text() == plain
    assert outputs[1].read_text() == render_text(report)
    assert 'href="#loc-1"' in outputs[2].read_text()


def test_html_partial_write_failure_names_both_completed_reports(tmp_path, capsys):
    path = ROOT / 'fixtures/open_chain.dxf'
    first, second, third = tmp_path / 'out.json', tmp_path / 'out.txt', tmp_path / 'absent' / 'out.html'
    with pytest.raises(SystemExit) as caught:
        main([str(path), '--json-report', str(first), '--text-report', str(second), '--html-report', str(third)])
    assert caught.value.code == 4
    captured = capsys.readouterr()
    assert captured.out == ''
    assert f'already written: {first}, {second}' in captured.err
    assert first.exists() and second.exists() and not third.exists()


def test_html_output_alias_created_during_analysis_is_rechecked(tmp_path, monkeypatch):
    from dxf_preflight import cli
    path = ROOT / 'fixtures/open_chain.dxf'
    first, html = tmp_path / 'out.json', tmp_path / 'out.html'
    result = bundle(path)

    def alias(*args, **kwargs):
        first.write_text('preserved')
        html.symlink_to(first)
        return result

    monkeypatch.setattr(cli, 'analyze_visual_supervised', alias)
    with pytest.raises(SystemExit) as caught:
        main([str(path), '--json-report', str(first), '--html-report', str(html)])
    assert caught.value.code == 2 and first.read_text() == 'preserved'


def test_subnormal_span_at_large_constant_other_axis_does_not_visually_collapse():
    report, geometry = synthetic([core.Segment((0.0, 1.0), (5e-324, 1.0), '0', 'A', 0)])
    tree = svg_tree(visual.render_html(report, geometry))
    line = next(e for e in tree.iter() if e.tag.endswith('line'))
    assert float(line.attrib['x2']) - float(line.attrib['x1']) == 720


def test_not_checked_entries_are_bounded_and_disclosed():
    report, geometry = bundle(ROOT / 'fixtures/open_chain.dxf')
    report['not_checked'] = ['x' * 256] * 10_000
    html = visual.render_html(report, geometry)
    assert 'Additional not-checked entries are omitted' in html
    assert html.count('x' * 256) == 64
    assert len(html) < 30_000


def test_segment_titles_keep_original_coordinates_even_without_findings():
    report, geometry = bundle(ROOT / 'fixtures/rectangle_lines.dxf')
    assert report['findings'] == []
    html = visual.render_html(report, geometry)
    assert '; start (0.0, 0.0); end (40.0, 0.0) drawing units' in html


@pytest.mark.parametrize('include_geometry', [False, True])
def test_exponent_overflow_in_report_coordinates_fails_closed(monkeypatch, include_geometry):
    path = ROOT / 'fixtures/open_chain.dxf'
    report, geometry = bundle(path)
    report['findings'][0]['details']['endpoints'][0]['point'][0] = 'OVERFLOW'
    final = {'kind': 'report', 'report': report}
    if include_geometry:
        final['geometry'] = geometry
    first = json.dumps({'kind': 'snapshot', 'path': str(path), 'sha256': report['input']['sha256']})
    second = json.dumps(final).replace('"OVERFLOW"', '1e999')
    monkeypatch.setattr(supervisor, '_worker_command', lambda: [PYTHON, '-c', f'print({first!r}); print({second!r})'])
    if include_geometry:
        result, payload = supervisor.analyze_visual_supervised(path, tolerance=1e-6, expected_unit='mm', timeout=5)
        assert payload is None
    else:
        result = supervisor.analyze_supervised(path, tolerance=1e-6, expected_unit='mm', timeout=5)
    assert result['status'] == 'incomplete'
    assert result['findings'][0]['rule_id'] == 'SCOPE009'
    json.dumps(result, allow_nan=False)
