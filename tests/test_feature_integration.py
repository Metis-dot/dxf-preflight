"""Original cross-feature probes: curve measurements never become plotted contours."""

from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import ezdxf
import pytest

from dxf_preflight import core, supervisor, visual

ROOT = Path(__file__).parents[1]


def bundle(path):
    captured = []
    report = core._analyze(path, expected_unit='mm', _on_geometry=captured.append)
    return report, captured[0] if captured else None


def text_content(html):
    class Text(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    parser = Text()
    parser.feed(html)
    return ' '.join(parser.parts)


def save(tmp_path, build):
    doc = ezdxf.new('R2010')
    doc.units = 4
    build(doc.modelspace())
    path = tmp_path / 'original_integration.dxf'
    doc.saveas(path)
    return path


@pytest.mark.parametrize('path', sorted((ROOT / 'fixtures').glob('*.dxf')), ids=lambda p: p.stem)
def test_html_discloses_separate_measurement_state_and_keeps_curve_geometry_out(path):
    before = path.read_bytes()
    report, geometry = bundle(path)
    original = deepcopy((report, geometry))
    html = visual.render_html(report, geometry)
    text = text_content(html)
    curves = report['summary']['curve_measurements']
    assert f"Curve measurement state: {curves['status']}" in text
    assert f"{curves['scanned_curve_entities']} scanned, {curves['measured_entities']} measured, {curves['skipped_entities']} skipped" in text
    assert 'Curve measurement budget: first 256 scanned modelspace CIRCLE/ARC entities' in text
    assert 'curve contour checks NOT RUN' in text
    assert 'Approximate values in drawing units' in text
    assert 'Curves are never drawn in this overview' in text
    assert original == (report, geometry)
    assert path.read_bytes() == before
    if curves['scanned_curve_entities']:
        assert report['status'] == 'incomplete'
        assert report['manual_review_required'] is True and report['gate_eligible'] is False
        assert 'SCOPE001' in html
    if geometry and geometry['segments']:
        svg = ET.fromstring(html[html.index('<svg '):html.index('</svg>') + 6])
        ns = {'s': 'http://www.w3.org/2000/svg'}
        base = svg.find("s:g[@class='base']", ns)
        assert len(base.findall('s:g/s:line', ns)) == len(geometry['segments'])
        assert not svg.findall('.//s:path', ns) and not svg.findall('.//s:ellipse', ns)
        assert all(c.get('class') == 'marker' for c in svg.findall('.//s:circle', ns))


def test_curve_only_measurements_do_not_fabricate_svg_or_locators(tmp_path):
    path = save(tmp_path, lambda m: (m.add_circle((17, -11), 3), m.add_arc((2, 4), 5, 270, 90)))
    report, geometry = bundle(path)
    assert report['summary']['curve_measurements']['measured_entities'] == 2
    assert geometry['segments'] == []
    html = visual.render_html(report, geometry)
    assert '<svg ' not in html and 'id="loc-' not in html
    assert 'Curve measurement state: checked' in html
    assert '2 scanned, 2 measured, 0 skipped' in html
    assert 'No supported snapshot geometry available to draw' in html


@pytest.mark.parametrize('kind', ['invalid_radius', 'non_xy', 'equal_arc_angles'])
def test_rejected_measurement_remains_unknown_and_unplotted(tmp_path, kind):
    def build(msp):
        if kind == 'invalid_radius':
            msp.add_circle((0, 0), 0)
        elif kind == 'non_xy':
            msp.add_circle((0, 0, 1e-12), 2)
        else:
            msp.add_arc((0, 0), 2, 0, 360)
    report, geometry = bundle(save(tmp_path, build))
    assert report['summary']['curve_measurements']['status'] == 'unknown'
    html = visual.render_html(report, geometry)
    assert 'Curve measurement state: unknown' in html
    assert '1 scanned, 0 measured, 1 skipped' in html
    assert '<svg ' not in html and 'id="loc-' not in html


def test_measurement_budget_and_scan_truncation_are_separate_unknowns(tmp_path, monkeypatch):
    path = save(tmp_path, lambda m: [m.add_circle((i * 10, 0), 2) for i in range(4)])
    monkeypatch.setattr(core, 'MAX_CURVE_MEASUREMENTS', 2)
    report, geometry = bundle(path)
    html = visual.render_html(report, geometry)
    assert 'Curve measurement state: unknown' in html
    assert '4 scanned, 2 measured, 2 skipped' in html
    assert 'Curve measurement budget: first 2 scanned modelspace CIRCLE/ARC entities' in html
    assert 'Entity extraction stopped early' not in html
    monkeypatch.setattr(core, 'MAX_ENTITIES', 1)
    report, geometry = bundle(path)
    html = visual.render_html(report, geometry)
    assert 'Curve measurement state: unknown' in html
    assert '1 scanned, 1 measured, 0 skipped' in html
    assert 'Entity extraction stopped early' in html
    assert 'The unscanned remainder is unknown' in html


def test_unreadable_and_failed_worker_have_explicit_unconfirmed_measurement_states(tmp_path, monkeypatch):
    report, geometry = bundle(tmp_path / 'absent.dxf')
    assert 'Curve measurement state: not_run' in visual.render_html(report, geometry)
    def crash(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 7, stdout='', stderr='controlled failure')
    monkeypatch.setattr(supervisor.subprocess, 'run', crash)
    report, geometry = supervisor.analyze_visual_supervised(ROOT / 'fixtures/curve_measurements.dxf', tolerance=1e-6, expected_unit='mm', timeout=30)
    html = visual.render_html(report, geometry)
    assert report['status'] == 'incomplete'
    assert 'Curve measurement state: unknown' in html
    assert '0 scanned, 0 measured, 0 skipped' in html
    assert '<svg ' not in html


def test_historical_schema_11_without_measurements_is_available_but_not_vacuously_checked():
    report, geometry = bundle(ROOT / 'fixtures/rectangle_lines.dxf')
    del report['summary']['curve_measurements']
    del report['scope']['measurement_only_entities']
    del report['scope']['limits']['max_curve_measurements']
    supervisor.VALIDATOR.validate(report)
    html = visual.render_html(report, geometry)
    assert 'Curve measurements unavailable in this report' in html
    assert 'Curve measurement state: checked' not in html
    json.dumps(report, allow_nan=False)
