"""The CLI writes reports only, and rejects output aliases of the input."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import tempfile

from . import __version__
from .core import EXPECTED_UNITS
from .supervisor import DEFAULT_TIMEOUT_SECONDS, analyze_supervised

EXIT_CODES = {"limited_checks_clear": 0, "issues_found": 1, "incomplete": 2, "unreadable": 3}


def _reference(ref: dict) -> str:
    return f"handle {ref.get('handle', '?')}, segment {ref.get('segment_index', '?')} (zero-based), layer {ref.get('layer', '?')!r}"


def _finding_rows(finding: dict) -> list[str]:
    """Compact CAD locators; complete metadata/style stays in the JSON report."""
    details = finding["details"]
    rows = []
    for key in ("endpoints", "nodes"):
        for node in details.get(key, []):
            refs = "; ".join(_reference(ref) for ref in node["entities"])
            degree = f", degree {node['degree']}" if "degree" in node else ""
            rows.append(f"At {node['point']}{degree}: {refs}")
    if "segments" in details:
        rows.extend(_reference(ref) for ref in details["segments"])
    if "entity" in details:
        rows.append(_reference(details["entity"]))
    for key in ("start", "end", "point", "contact_points", "overlap_endpoints", "clusters"):
        if key in details:
            label = "point (approximate display)" if key == "point" and details.get("point_is_approximate") else key
            rows.append(f"{label}: {details[key]}")
    if not rows:
        rows.extend(f"{key}: {value}" for key, value in sorted(details.items()))
    rule = finding["rule_id"]
    if rule.startswith("FILE"):
        next_step = "use a stable, readable local DXF and rerun; do not change it during analysis."
    elif rule.startswith("UNIT"):
        next_step = "verify the original CAD unit declaration and intended size; do not infer or rescale from this report."
    elif rule in {"SCOPE007", "SCOPE009"}:
        next_step = "review the incomplete/resource reason; use a small trusted drawing and appropriate isolated environment before retrying."
    else:
        next_step = "locate these references/coordinates in the original CAD drawing and review intent; no automatic edit is advised."
    rows.append("Next: " + next_step)
    return ["    " + row for row in rows]


def render_text(report: dict) -> str:
    lines = [
        f"DXF Preflight prototype v{report['tool']['version']}",
        "MANUAL REVIEW REQUIRED: Manufacturing checks are incomplete; this report is never eligible as a production gate.",
        f"Status: {report['status']}",
        f"Input: {report['input']['path']}",
        f"SHA-256: {report['input']['sha256'] or 'not available'}",
        f"Final source bytes match captured snapshot: {report['input']['unchanged_during_analysis']}",
        f"Endpoint tolerance: {report['parameters']['endpoint_tolerance']} drawing units",
    ]
    if "units" in report:
        unit = report["units"]
        lines.append(f"Declared units: {unit['name']} ($INSUNITS={unit['code']}); expected: {unit['expected'] or 'not specified'}")
    s = report["summary"]
    lines.append(f"Entities: {s['modelspace_entities']} scanned, {s['supported_entities']} supported, {s['unsupported_entities']} unsupported")
    lines.append(f"Segments: {s['extracted_segments']} extracted, {s['unique_nondegenerate_segments']} unique nondegenerate")
    lines.append("Check states: " + ", ".join(f"{name}={state}" for name, state in report["checks"].items()))
    lines.extend(["", "Findings:"])
    if not report["findings"]:
        lines.append("  No findings in the limited checks listed above. This is not production approval.")
    unsupported = {}
    for finding in report["findings"]:
        if finding["rule_id"] == "SCOPE001":
            details = finding["details"]
            unsupported.setdefault(details["entity_type"], []).append(details["handle"])
            continue
        lines.append(f"  [{finding['rule_id']}] {finding['severity'].upper()}: {finding['message']}")
        lines.extend(_finding_rows(finding))
    for kind, handles in sorted(unsupported.items()):
        lines.append(f"  [SCOPE001] BLOCKER: Unsupported {kind}: {len(handles)} entities")
        lines.append(f"    Representative handles ({min(8, len(handles))} of {len(handles)}): {', '.join(handles[:8])}; all findings remain in JSON")
        lines.append("    Next: inspect unsupported content in CAD; this tool did not check it or approximate it.")
    lines.extend(["", "Not checked:"] + [f"  - {item}" for item in report["not_checked"]])
    lines.extend(["", report["disclaimer"]])
    return "\n".join(lines) + "\n"


def _tolerance(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("tolerance must be a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("tolerance must be finite and greater than zero")
    return value


def _same_path(a: Path, b: Path) -> bool:
    if a.resolve() == b.resolve():
        return True
    return a.exists() and b.exists() and os.path.samefile(a, b)


def _atomic_write(path: Path, content: str) -> None:
    # The caller rejects input aliases before any output is opened.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only, limited 2D DXF preflight. All outputs require manual review and are ineligible as a production gate. Exit 0 means only that the explicitly limited checks completed without findings. No certification or repair.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--tolerance", type=_tolerance, default=1e-6, help="Endpoint distance in drawing units (default: 1e-6); no rounding or scaling")
    parser.add_argument("--expected-unit", choices=sorted(EXPECTED_UNITS), help="Compare with $INSUNITS; never infer, repair or scale")
    parser.add_argument("--timeout", type=_tolerance, default=DEFAULT_TIMEOUT_SECONDS, help="Analysis worker wall-clock seconds (default: 30); not a memory/CPU sandbox. API analyze() remains in-process")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="stdout format")
    parser.add_argument("--json-report", type=Path, help="Optional JSON output file; parent folder must exist")
    parser.add_argument("--text-report", type=Path, help="Optional human-readable output file; parent folder must exist")
    args = parser.parse_args(argv)
    outputs = [p for p in (args.json_report, args.text_report) if p is not None]
    try:
        if any(_same_path(args.input, output) for output in outputs):
            parser.error("a report output cannot overwrite or alias the input DXF")
        if len(outputs) == 2 and _same_path(*outputs):
            parser.error("JSON and text outputs must have different paths")
    except (OSError, RuntimeError) as exc:
        parser.error(f"unable to validate report paths: {exc}")
    report = analyze_supervised(args.input, tolerance=args.tolerance, expected_unit=args.expected_unit, timeout=args.timeout)
    text = render_text(report)
    json_text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    written = []
    try:
        # Recheck after analysis as a basic guard against accidental path changes.
        for output in outputs:
            if _same_path(args.input, output):
                parser.error("a report output now aliases the input DXF")
        if len(outputs) == 2 and _same_path(*outputs):
            parser.error("JSON and text outputs now alias each other")
        if args.json_report:
            _atomic_write(args.json_report, json_text)
            written.append(str(args.json_report))
        if args.text_report:
            _atomic_write(args.text_report, text)
            written.append(str(args.text_report))
    except (OSError, RuntimeError) as exc:
        completed = "; already written: " + ", ".join(written) if written else "; no requested report was written"
        parser.exit(4, f"Report write failed: {exc}{completed}\n")
    print(json_text if args.format == "json" else text, end="")
    return EXIT_CODES[report["status"]]
