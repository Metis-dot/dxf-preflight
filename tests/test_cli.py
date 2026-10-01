import json
import os
from pathlib import Path
import subprocess
import sys

import ezdxf
import pytest

from dxf_preflight.cli import main


@pytest.fixture
def input_path(tmp_path):
    doc = ezdxf.new("R2010")
    doc.units = 4
    doc.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
    path = tmp_path / "input.dxf"
    doc.saveas(path)
    return path


def test_cli_emits_valid_json_and_both_reports_without_input_change(input_path, capsys):
    before = input_path.read_bytes()
    json_path = input_path.parent / "report.json"
    text_path = input_path.parent / "report.txt"
    assert main([str(input_path), "--format", "json", "--json-report", str(json_path), "--text-report", str(text_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert json.loads(json_path.read_text()) == report
    assert "Status: limited_checks_clear" in text_path.read_text()
    assert "MANUAL REVIEW REQUIRED" in text_path.read_text().splitlines()[1]
    assert report["manual_review_required"] is True and report["gate_eligible"] is False
    assert "not production approval" in text_path.read_text()
    assert input_path.read_bytes() == before


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_cli_rejects_any_input_alias_for_report(input_path, alias):
    output = input_path
    if alias != "same":
        output = input_path.parent / "alias.dxf"
        if alias == "symlink": output.symlink_to(input_path)
        else: os.link(input_path, output)
    before = input_path.read_bytes()
    with pytest.raises(SystemExit) as exc:
        main([str(input_path), "--json-report", str(output)])
    assert exc.value.code == 2
    assert input_path.read_bytes() == before


def test_reports_cannot_share_output_path(input_path):
    path = input_path.parent / "report"
    with pytest.raises(SystemExit) as exc:
        main([str(input_path), "--json-report", str(path), "--text-report", str(path)])
    assert exc.value.code == 2
    assert not path.exists()


def test_output_failure_has_separate_exit_code(input_path):
    with pytest.raises(SystemExit) as exc:
        main([str(input_path), "--json-report", str(input_path.parent / "absent" / "report.json")])
    assert exc.value.code == 4


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-1", "nonsense"])
def test_cli_rejects_invalid_tolerances(input_path, value):
    with pytest.raises(SystemExit) as exc:
        main([str(input_path), "--tolerance", value])
    assert exc.value.code == 2


def test_exit_codes_for_issues_incomplete_and_unreadable(input_path, capsys):
    assert main([str(input_path), "--expected-unit", "in"]) == 1
    doc = ezdxf.readfile(input_path)
    doc.modelspace().add_circle((20, 20), 5)
    doc.saveas(input_path)
    assert main([str(input_path)]) == 2
    assert main([str(input_path.parent / "missing")]) == 3
    capsys.readouterr()


def test_module_entrypoint_json_is_parseable(input_path):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1] / "src"))
    result = subprocess.run([sys.executable, "-m", "dxf_preflight", str(input_path), "--format", "json"], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "limited_checks_clear"


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "4.0"])
@pytest.mark.parametrize("format", ["json", "text"])
def test_malformed_noninteger_units_never_crash_json_or_text(input_path, capsys, value, format):
    raw = input_path.read_text()
    original = "$INSUNITS\n 70\n4\n"
    assert original in raw
    input_path.write_text(raw.replace(original, f"$INSUNITS\n 40\n{value}\n"))
    before = input_path.read_bytes()
    assert main([str(input_path), "--format", format]) == 2
    output = capsys.readouterr().out
    assert output
    if format == "json":
        report = json.loads(output)
        assert report["units"]["raw_value_type"] == "float"
        assert report["status"] == "incomplete"
    else:
        assert "Status: incomplete" in output
    assert input_path.read_bytes() == before


@pytest.mark.parametrize('value', ['nan', 'inf', '0', '-1', 'nonsense'])
def test_cli_rejects_invalid_worker_timeout(input_path, value):
    with pytest.raises(SystemExit) as exc:
        main([str(input_path), '--timeout', value])
    assert exc.value.code == 2


def test_unicode_and_space_paths_existing_reports_are_replaced(input_path, capsys):
    renamed = input_path.parent / '原创 contour 空格.dxf'
    input_path.rename(renamed)
    before = renamed.read_bytes()
    json_path = renamed.parent / '结果 report.json'
    text_path = renamed.parent / '结果 report.txt'
    json_path.write_text('old JSON', encoding='utf-8')
    text_path.write_text('old text', encoding='utf-8')
    assert main([str(renamed), '--format', 'json', '--json-report', str(json_path), '--text-report', str(text_path)]) == 0
    stdout = capsys.readouterr().out
    report = json.loads(stdout)
    assert report == json.loads(json_path.read_text(encoding='utf-8'))
    assert report['input']['path'] == str(renamed)
    assert 'old text' not in text_path.read_text(encoding='utf-8')
    assert renamed.read_bytes() == before
    assert sorted(p.name for p in renamed.parent.iterdir()) == sorted([renamed.name, json_path.name, text_path.name])


@pytest.mark.parametrize('alias', ['symlink', 'hardlink'])
def test_report_outputs_cannot_alias_each_other(input_path, alias):
    first = input_path.parent / 'first.json'
    first.write_text('preserved', encoding='utf-8')
    second = input_path.parent / 'second.txt'
    if alias == 'symlink':
        second.symlink_to(first)
    else:
        os.link(first, second)
    with pytest.raises(SystemExit) as exc:
        main([str(input_path), '--json-report', str(first), '--text-report', str(second)])
    assert exc.value.code == 2
    assert first.read_text() == second.read_text() == 'preserved'


def test_two_output_partial_success_is_explicit(input_path, capsys):
    first = input_path.parent / 'written.json'
    missing = input_path.parent / 'no parent' / 'not-written.txt'
    before = input_path.read_bytes()
    with pytest.raises(SystemExit) as exc:
        main([str(input_path), '--json-report', str(first), '--text-report', str(missing)])
    assert exc.value.code == 4
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'already written: ' + str(first) in captured.err
    assert json.loads(first.read_text())['status'] == 'limited_checks_clear'
    assert not missing.exists()
    assert input_path.read_bytes() == before


def test_permission_failure_is_explicit_and_temp_file_is_cleaned(input_path, capsys, monkeypatch):
    from dxf_preflight import cli
    output = input_path.parent / 'denied.json'
    def deny_replace(*args, **kwargs):
        raise PermissionError('controlled denied output replacement')
    monkeypatch.setattr(cli.os, 'replace', deny_replace)
    with pytest.raises(SystemExit) as exc:
        main([str(input_path), '--json-report', str(output)])
    assert exc.value.code == 4
    assert 'no requested report was written' in capsys.readouterr().err
    assert list(input_path.parent.iterdir()) == [input_path]


def test_output_collisions_created_during_analysis_are_rejected(input_path, monkeypatch):
    from dxf_preflight import cli, analyze
    first = input_path.parent / 'first.json'
    second = input_path.parent / 'second.txt'
    def create_alias(*args, **kwargs):
        first.write_text('preserved', encoding='utf-8')
        second.symlink_to(first)
        return analyze(input_path)
    monkeypatch.setattr(cli, 'analyze_supervised', create_alias)
    with pytest.raises(SystemExit) as exc:
        main([str(input_path), '--json-report', str(first), '--text-report', str(second)])
    assert exc.value.code == 2
    assert first.read_text() == 'preserved'


def test_cli_real_analysis_deadline_returns_json_incomplete(input_path, capsys):
    before = input_path.read_bytes()
    assert main([str(input_path), '--format', 'json', '--timeout', '0.000001']) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'incomplete'
    assert report['execution']['mode'] == 'subprocess'
    assert report['execution']['sandboxed'] is False
    assert report['findings'][0]['details']['failure'] == 'wall_clock_timeout'
    assert report['input']['unchanged_during_analysis'] is None
    assert input_path.read_bytes() == before


def test_text_locates_open_ends_without_json_detail_dump():
    from dxf_preflight import analyze
    from dxf_preflight.cli import render_text
    root = Path(__file__).parents[1]
    report = analyze(root / 'fixtures/open_chain.dxf')
    text = render_text(report)
    assert 'At [0.0, 0.0]: handle 2F, segment 0 (zero-based), layer' in text
    assert 'At [0.0, 20.0]: handle 2F, segment 2 (zero-based), layer' in text
    assert '"entities"' not in text
    assert 'Next: locate' in text


def test_text_unsupported_summary_keeps_all_details_in_json(input_path):
    from dxf_preflight import analyze
    from dxf_preflight.cli import render_text
    doc = ezdxf.readfile(input_path)
    for index in range(10):
        doc.modelspace().add_arc((index, 0), 1, 0, 90)
    doc.saveas(input_path)
    report = analyze(input_path)
    text = render_text(report)
    assert 'Unsupported ARC: 10 entities' in text
    assert 'Representative handles (8 of 10)' in text
    assert len([f for f in report['findings'] if f['rule_id'] == 'SCOPE001']) == 10
    assert text.count('[SCOPE001]') == 1


def test_self_referential_output_symlink_is_controlled(input_path, capsys):
    output = input_path.parent / 'loop.json'
    output.symlink_to(output.name)
    with pytest.raises(SystemExit) as exc:
        main([str(input_path), '--json-report', str(output)])
    assert exc.value.code == 2
    assert 'unable to validate report paths' in capsys.readouterr().err
