"""CLI-only worker wall-clock boundary, including hashing; not a sandbox."""

from __future__ import annotations

from collections import Counter
from importlib.resources import files
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from jsonschema import Draft202012Validator, ValidationError

from . import __version__
from .core import _finding, _finish, _new_report

DEFAULT_TIMEOUT_SECONDS = 30.0
VALIDATOR = Draft202012Validator(json.loads(files('dxf_preflight').joinpath('report.schema.json').read_text(encoding='utf-8')))


def _worker_command() -> list[str]:
    return [sys.executable, '-m', 'dxf_preflight._worker']


def _reject_constant(value: str):
    raise ValueError(f'Non-finite JSON constant: {value}')


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Non-finite JSON number')
    return number


def _loads(text: str):
    return json.loads(text, parse_constant=_reject_constant, parse_float=_finite_float)


def _snapshot_record(stdout: str | bytes | None, path: Path) -> str | None:
    """Only a complete, validated initial worker record can supply a hash."""
    try:
        if isinstance(stdout, bytes):
            stdout = stdout.split(b'\n', 1)[0].decode('utf-8')
        record = _loads((stdout or '').split('\n', 1)[0])
        if not isinstance(record, dict) or record.get('kind') != 'snapshot' or record.get('path') != str(path):
            return None
        digest = record.get('sha256')
        return digest if isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) else None
    except (ValueError, TypeError, IndexError, RecursionError):
        return None


def _check_worker_result(report: object, request: dict | None = None) -> dict:
    """Validate the complete packaged schema and transport semantics, fail closed."""
    try:
        VALIDATOR.validate(report)
    except ValidationError as exc:
        raise ValueError('Worker result does not match report schema') from exc
    if report['tool']['version'] != __version__ or report['execution']['mode'] != 'in_process':
        raise ValueError('Wrong worker version/execution mode')
    if request is not None and (
        report['input']['path'] != request['path']
        or report['parameters']['endpoint_tolerance'] != request['tolerance']
        or report['parameters']['expected_unit'] != request['expected_unit']
        or ('units' in report and report['units']['expected'] != request['expected_unit'])
    ):
        raise ValueError('Worker report does not match requested input/options')
    counts = Counter(f['severity'] for f in report['findings'])
    if report['summary']['finding_counts'] != {key: counts[key] for key in ('blocker', 'error', 'warning')}:
        raise ValueError('Finding counts contradict actual findings')
    original_status = report['status']
    original_coverage = report['coverage_complete_for_declared_subset']
    _finish(report, unreadable=original_status == 'unreadable')
    if report['status'] != original_status or report['coverage_complete_for_declared_subset'] != original_coverage:
        raise ValueError('Status/coverage contradict actual findings/check states')
    return report


def _analyze_supervised(path: Path, *, tolerance: float, expected_unit: str | None, timeout: float, include_geometry: bool = False) -> tuple[dict, dict | None]:
    """The fixed worker hashes, parses and analyzes inside one wall deadline.

    subprocess.run kills and reaps its direct child on timeout. Parent path
    checks, result validation and report writing are outside this deadline.
    """
    request = {'path': str(path), 'tolerance': tolerance, 'expected_unit': expected_unit}
    geometry = None
    if include_geometry:
        request['include_geometry'] = True
    reason = None
    rule = 'SCOPE009'
    before_hash = None
    try:
        # This parent-owned private directory lets us remove parser snapshots
        # after the direct worker exits, crashes or is killed on its deadline.
        with tempfile.TemporaryDirectory(prefix='dxf-preflight-worker-') as directory:
            env = dict(os.environ, TMPDIR=directory)
            result = subprocess.run(
                _worker_command(), input=json.dumps(request, allow_nan=False), env=env,
                capture_output=True, text=True, encoding='utf-8', timeout=timeout, check=False,
            )
        before_hash = _snapshot_record(result.stdout, path)
        if result.returncode:
            reason = {'failure': 'worker_exit', 'returncode': result.returncode}
        else:
            records = result.stdout.split('\n')
            if records and records[-1] == '':
                records.pop()
            if len(records) != 2:
                raise ValueError('Worker protocol requires snapshot and report records')
            initial = _loads(records[0])
            if initial != {'kind': 'snapshot', 'path': str(path), 'sha256': before_hash}:
                raise ValueError('Invalid initial snapshot record')
            final = _loads(records[1])
            if not isinstance(final, dict) or final.get('kind') != 'report' or set(final) != ({'kind', 'report', 'geometry'} if include_geometry else {'kind', 'report'}):
                raise ValueError('Invalid final report record')
            report = _check_worker_result(final['report'], request)
            if include_geometry:
                from .visual import validate_geometry
                geometry = validate_geometry(final['geometry'], report)
            if report['input']['sha256'] != before_hash:
                raise ValueError('Initial hash and captured report hash disagree')
    except subprocess.TimeoutExpired as exc:
        before_hash = _snapshot_record(exc.stdout, path)
        rule = 'SCOPE007'
        reason = {'failure': 'wall_clock_timeout', 'timeout_seconds': timeout}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        reason = {'failure': 'worker_start_or_result', 'exception_type': type(exc).__name__}
    if reason is not None:
        geometry = None
        report = _new_report(path, tolerance, expected_unit)
        report['input']['sha256'] = before_hash
        # A failed worker established no stable analyzed snapshot. Even matching
        # pre/post bytes would not confirm that interrupted checks completed.
        report['checks'] = {name: 'unknown' for name in report['checks']}
        report['checks']['input_read'] = 'checked' if before_hash else 'unknown'
        report['summary']['segment_intersections']['status'] = 'unknown'
        _finding(report, rule, 'blocker', 'Analysis worker did not complete; no clear result is available.', **reason)
        _finish(report)
    report['execution'] = {
        'mode': 'subprocess', 'wall_clock_timeout_seconds': timeout,
        'hard_memory_limit': False, 'hard_cpu_limit': False, 'sandboxed': False,
    }
    return report, geometry


def analyze_supervised(path: Path, *, tolerance: float, expected_unit: str | None, timeout: float) -> dict:
    """Existing report-only API/worker protocol; no display payload is requested."""
    return _analyze_supervised(path, tolerance=tolerance, expected_unit=expected_unit, timeout=timeout)[0]


def analyze_visual_supervised(path: Path, *, tolerance: float, expected_unit: str | None, timeout: float) -> tuple[dict, dict | None]:
    """Capture bounded display geometry in the same worker/snapshot as checks."""
    return _analyze_supervised(path, tolerance=tolerance, expected_unit=expected_unit, timeout=timeout, include_geometry=True)
