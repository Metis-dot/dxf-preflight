"""Original synthetic status examples and conservative schema invariants."""

from copy import deepcopy
from importlib.resources import files
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import time

import ezdxf
import jsonschema
import pytest

from dxf_preflight import analyze, core
from dxf_preflight import supervisor

ROOT = Path(__file__).parents[1]
SCHEMA = json.loads(files('dxf_preflight').joinpath('report.schema.json').read_text(encoding='utf-8'))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def validate(report):
    VALIDATOR.validate(report)
    assert report['summary']['segment_intersections']['status'] == report['checks']['segment_intersections']
    assert report['manual_review_required'] is True
    assert report['gate_eligible'] is False


def test_schema_is_valid_and_is_a_packaged_resource():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA['properties']['schema_version']['const'] == '1.1'


@pytest.mark.parametrize('path', sorted((ROOT / 'fixtures').glob('*.dxf')), ids=lambda p: p.stem)
def test_every_original_fixture_and_saved_report_validate(path):
    report = analyze(path, expected_unit='mm')
    validate(report)
    saved = json.loads((ROOT / 'reports' / (path.stem + '.json')).read_text(encoding='utf-8'))
    validate(saved)
    assert saved['checks'] == report['checks']


@pytest.mark.parametrize('missing', [False, True])
def test_unreadable_shapes_validate(tmp_path, missing):
    path = tmp_path / 'bad.dxf'
    if not missing:
        path.write_bytes(b'not a DXF')
    report = analyze(path)
    validate(report)
    assert report['status'] == 'unreadable'
    assert report['checks']['parsing'] != 'checked'
    assert report['checks']['topology'] == 'not_run'


@pytest.mark.parametrize('value', ['nan', 'inf', '-inf', '4.0'])
def test_malformed_unit_values_validate(tmp_path, value):
    path = tmp_path / 'units.dxf'
    path.write_bytes((ROOT / 'fixtures/rectangle_lines.dxf').read_bytes().replace(b'$INSUNITS\n 70\n4\n', f'$INSUNITS\n 40\n{value}\n'.encode()))
    report = analyze(path)
    validate(report)
    assert report['status'] == 'incomplete'


@pytest.mark.parametrize('limit', ['MAX_FILE_BYTES', 'MAX_ENTITIES', 'MAX_SEGMENTS', 'MAX_COMPARISONS'])
def test_resource_statuses_validate_and_never_hide_skipped_checks(monkeypatch, limit):
    monkeypatch.setattr(core, limit, 1)
    report = analyze(ROOT / 'fixtures/tolerance_gap.dxf')
    validate(report)
    assert report['status'] == 'incomplete'
    assert any(state != 'checked' for state in report['checks'].values())
    if limit == 'MAX_ENTITIES':
        assert report['checks']['scope'] == report['checks']['segment_extraction'] == 'unknown'
        assert report['checks']['duplicates'] == report['checks']['topology'] == report['checks']['segment_intersections'] == 'unknown'


def test_ambiguous_layer_is_unknown_not_checked(tmp_path):
    doc = ezdxf.new('R2010')
    doc.units = 4
    for point in [(0, 0), (0.75e-6, 0), (1.5e-6, 0)]:
        doc.modelspace().add_line(point, (10, 10))
    path = tmp_path / 'ambiguous.dxf'
    doc.saveas(path)
    report = analyze(path)
    validate(report)
    assert report['checks']['topology'] == 'unknown'
    assert report['summary']['layers'][0]['status'] == 'incomplete'


@pytest.mark.parametrize('state', ['not_run', 'unknown'])
def test_schema_rejects_clear_with_an_unconfirmed_check(state):
    report = analyze(ROOT / 'fixtures/rectangle_lines.dxf')
    report['checks']['topology'] = state
    with pytest.raises(jsonschema.ValidationError):
        validate(report)
    with pytest.raises(ValueError):
        supervisor._check_worker_result(deepcopy(report))


@pytest.mark.parametrize('field,value', [('manual_review_required', False), ('gate_eligible', True), ('read_only', False)])
def test_schema_rejects_relaxed_review_fields(field, value):
    report = analyze(ROOT / 'fixtures/rectangle_lines.dxf')
    report[field] = value
    with pytest.raises(jsonschema.ValidationError):
        validate(report)


def test_real_controlled_worker_timeout_kills_and_reaps_process(tmp_path, monkeypatch):
    # This local test-only worker is deliberately controlled source, not input code.
    marker = tmp_path / 'worker_started'
    path = ROOT / 'fixtures/rectangle_lines.dxf'
    initial = json.dumps({'kind': 'snapshot', 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    script = "import os,time,pathlib; pathlib.Path(%r).write_text(str(os.getpid())); print(%r, flush=True); time.sleep(60)" % (str(marker), initial)
    monkeypatch.setattr(supervisor, '_worker_command', lambda: [sys.executable, '-c', script])
    path = ROOT / 'fixtures/rectangle_lines.dxf'
    before = path.read_bytes()
    started = time.monotonic()
    report = supervisor.analyze_supervised(path, tolerance=1e-6, expected_unit='mm', timeout=0.5)
    assert time.monotonic() - started < 5
    validate(report)
    assert report['status'] == 'incomplete'
    assert report['findings'][0]['details']['failure'] == 'wall_clock_timeout'
    assert report['input']['sha256'] is not None
    assert report['input']['unchanged_during_analysis'] is None
    assert report['checks']['topology'] == 'unknown'
    assert path.read_bytes() == before
    assert marker.exists(), 'controlled worker did not start before deadline'
    pid = int(marker.read_text())
    # Linux /proc disappears after subprocess.run has killed and waited.
    if sys.platform.startswith('linux'):
        assert not Path(f'/proc/{pid}').exists()


@pytest.mark.parametrize('script', ["import sys; sys.exit(7)", "print('not JSON')", "print('{}')", "print('{\"status\": \"limited_checks_clear\"}')"])
def test_controlled_worker_crash_or_bad_result_is_incomplete(monkeypatch, script):
    monkeypatch.setattr(supervisor, '_worker_command', lambda: [sys.executable, '-c', script])
    report = supervisor.analyze_supervised(ROOT / 'fixtures/rectangle_lines.dxf', tolerance=1e-6, expected_unit=None, timeout=5)
    validate(report)
    assert report['status'] == 'incomplete'
    assert report['findings'][0]['rule_id'] == 'SCOPE009'
    assert report['input']['unchanged_during_analysis'] is None


def test_worker_start_failure_is_incomplete(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('controlled start failure')
    monkeypatch.setattr(subprocess, 'run', fail)
    report = supervisor.analyze_supervised(ROOT / 'fixtures/rectangle_lines.dxf', tolerance=1e-6, expected_unit=None, timeout=5)
    validate(report)
    assert report['status'] == 'incomplete'


def test_api_remains_in_process_and_repeatable():
    first = analyze(ROOT / 'fixtures/rectangle_lines.dxf', expected_unit='mm')
    assert first == analyze(ROOT / 'fixtures/rectangle_lines.dxf', expected_unit='mm')
    assert first['execution']['mode'] == 'in_process'
    assert first['execution']['wall_clock_timeout_seconds'] is None


def test_timeout_during_initial_hash_has_no_fabricated_hash(tmp_path, monkeypatch):
    marker = tmp_path / 'hash_started'
    script = "from dxf_preflight import _worker,core; import pathlib,time\ndef slow(path):\n pathlib.Path(%r).write_text('started')\n time.sleep(60)\ncore._capture_bytes = slow\n_worker.main()" % str(marker)
    monkeypatch.setattr(supervisor, '_worker_command', lambda: [sys.executable, '-c', script])
    start = time.monotonic()
    report = supervisor.analyze_supervised(ROOT / 'fixtures/rectangle_lines.dxf', tolerance=1e-6, expected_unit=None, timeout=1)
    assert time.monotonic() - start < 5
    assert marker.exists()
    validate(report)
    assert report['status'] == 'incomplete'
    assert report['input']['sha256'] is None
    assert report['input']['unchanged_during_analysis'] is None
    assert report['checks']['input_read'] == 'unknown'


@pytest.mark.parametrize('mutation', [
    'missing_units', 'missing_entity_count', 'missing_tolerance',
    'intersection_mismatch', 'wrong_path', 'wrong_tolerance',
    'wrong_expected_unit', 'wrong_finding_counts', 'false_coverage',
])
def test_full_looking_invalid_worker_reports_fail_closed(monkeypatch, mutation):
    path = ROOT / 'fixtures/rectangle_lines.dxf'
    report = analyze(path, expected_unit='mm')
    if mutation == 'missing_units': del report['units']
    elif mutation == 'missing_entity_count': del report['summary']['modelspace_entities']
    elif mutation == 'missing_tolerance': del report['parameters']['endpoint_tolerance']
    elif mutation == 'intersection_mismatch': report['summary']['segment_intersections']['status'] = 'unknown'
    elif mutation == 'wrong_path': report['input']['path'] = 'another.dxf'
    elif mutation == 'wrong_tolerance': report['parameters']['endpoint_tolerance'] = 0.1
    elif mutation == 'wrong_expected_unit': report['parameters']['expected_unit'] = 'in'
    elif mutation == 'wrong_finding_counts': report['summary']['finding_counts']['error'] = 1
    elif mutation == 'false_coverage': report['coverage_complete_for_declared_subset'] = False
    initial = json.dumps({'kind': 'snapshot', 'path': str(path), 'sha256': report['input']['sha256']})
    final = json.dumps({'kind': 'report', 'report': report})
    script = 'print(%r); print(%r)' % (initial, final)
    monkeypatch.setattr(supervisor, '_worker_command', lambda: [sys.executable, '-c', script])
    result = supervisor.analyze_supervised(path, tolerance=1e-6, expected_unit='mm', timeout=5)
    validate(result)
    assert result['status'] == 'incomplete'
    assert result['findings'][0]['rule_id'] == 'SCOPE009'


def test_deep_worker_transport_recursion_is_controlled(monkeypatch):
    script = "print('{\"a\":'+ '['*10000+'0'+']'*10000+'}')"
    monkeypatch.setattr(supervisor, '_worker_command', lambda: [sys.executable, '-c', script])
    report = supervisor.analyze_supervised(ROOT / 'fixtures/rectangle_lines.dxf', tolerance=1e-6, expected_unit=None, timeout=5)
    validate(report)
    assert report['status'] == 'incomplete'


def test_worker_private_directory_is_removed_after_timeout(tmp_path, monkeypatch):
    import os
    marker = tmp_path / 'worker_temp_path'
    script = "import os,pathlib,time; folder=pathlib.Path(os.environ['TMPDIR']); (folder/'captured.dxf').write_bytes(b'controlled snapshot'); pathlib.Path(%r).write_text(str(folder)); time.sleep(60)" % str(marker)
    monkeypatch.setattr(supervisor, '_worker_command', lambda: [sys.executable, '-c', script])
    report = supervisor.analyze_supervised(ROOT / 'fixtures/rectangle_lines.dxf', tolerance=1e-6, expected_unit=None, timeout=0.5)
    validate(report)
    assert marker.exists()
    assert not Path(marker.read_text()).exists()


def test_completed_hash_record_survives_later_invalid_utf8_on_timeout(monkeypatch):
    path = ROOT / 'fixtures/rectangle_lines.dxf'
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    initial = json.dumps({'kind': 'snapshot', 'path': str(path), 'sha256': digest})
    script = "import sys,time; print(%r, flush=True); sys.stdout.buffer.write(b'\\xff'); sys.stdout.buffer.flush(); time.sleep(60)" % initial
    monkeypatch.setattr(supervisor, '_worker_command', lambda: [sys.executable, '-c', script])
    report = supervisor.analyze_supervised(path, tolerance=1e-6, expected_unit=None, timeout=0.5)
    validate(report)
    assert report['status'] == 'incomplete'
    assert report['input']['sha256'] == digest
    assert report['input']['unchanged_during_analysis'] is None


def test_all_saved_text_examples_match_persisted_json_renderer():
    from dxf_preflight.cli import render_text
    for path in sorted((ROOT / 'reports').glob('*.json')):
        if path.name == 'fixture_summary.json':
            continue
        report = json.loads(path.read_text(encoding='utf-8'))
        assert path.with_suffix('.txt').read_text(encoding='utf-8') == render_text(report)
