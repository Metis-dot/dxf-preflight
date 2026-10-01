"""Bounded, offline HTML/SVG overview of the exact supported snapshot subset.

Display geometry is a separate private worker payload, never part of report
schema 1.1. No second DXF parse, arbitrary file reads, scripts or remote assets.
"""

from __future__ import annotations

from collections import Counter
from html import escape
from fractions import Fraction
import math

MAX_DISPLAY_SEGMENTS = 2_000
MAX_DISPLAY_FINDINGS = 256
MAX_DISPLAY_MARKERS = 512
MAX_LOCATORS_PER_FINDING = 24
MAX_TEXT_CHARS = 256
MAX_NOT_CHECKED_ITEMS = 64


def _short(value) -> str:
    text = str(value)
    return text if len(text) <= MAX_TEXT_CHARS else text[:MAX_TEXT_CHARS] + "… [shortened]"


def _safe(value) -> str:
    return escape(_short(value), quote=True)


def capture_geometry(segments, report: dict, *, scan_complete: bool) -> dict:
    """Called only inside the original analysis worker after bounded extraction."""
    display = []
    for segment in segments[:MAX_DISPLAY_SEGMENTS]:
        truncated = len(segment.entity) > MAX_TEXT_CHARS or len(segment.layer) > MAX_TEXT_CHARS
        display.append({
            "start": list(segment.start), "end": list(segment.end),
            "handle": segment.entity[:MAX_TEXT_CHARS], "layer": segment.layer[:MAX_TEXT_CHARS],
            "segment_index": segment.part, "locator_shortened": truncated,
        })
    return {
        "sha256": report["input"]["sha256"], "extracted_segments": len(segments),
        "scan_complete": scan_complete, "segments": display,
    }


def _point(value) -> bool:
    try:
        return (type(value) in (list, tuple) and len(value) == 2
                and all(type(v) in (int, float) and math.isfinite(v) for v in value))
    except OverflowError:
        return False


def validate_geometry(value: object, report: dict) -> dict | None:
    """Fail closed on mismatched, nonfinite, oversized or malformed transport."""
    if value is None:
        if report["checks"]["parsing"] == "checked":
            raise ValueError("Parsed worker omitted requested display geometry")
        return None
    if type(value) is not dict or set(value) != {"sha256", "extracted_segments", "scan_complete", "segments"}:
        raise ValueError("Invalid display payload")
    if (report["checks"]["parsing"] != "checked" or value["sha256"] != report["input"]["sha256"]
            or type(value["extracted_segments"]) is not int
            or value["extracted_segments"] != report["summary"]["extracted_segments"]
            or type(value["scan_complete"]) is not bool
            or value["scan_complete"] != (report["checks"]["scope"] == "checked")):
        raise ValueError("Display payload does not match analysis")
    segments = value["segments"]
    if type(segments) is not list or len(segments) != min(value["extracted_segments"], MAX_DISPLAY_SEGMENTS):
        raise ValueError("Invalid display segment count")
    for segment in segments:
        if type(segment) is not dict or set(segment) != {"start", "end", "handle", "layer", "segment_index", "locator_shortened"}:
            raise ValueError("Invalid display segment")
        if (not _point(segment["start"]) or not _point(segment["end"])
                or type(segment["segment_index"]) is not int
                or not 0 <= segment["segment_index"] <= report["scope"]["limits"]["max_segments"]
                or type(segment["locator_shortened"]) is not bool
                or any(type(segment[k]) is not str or len(segment[k]) > MAX_TEXT_CHARS for k in ("handle", "layer"))):
            raise ValueError("Invalid display coordinates/locator")
    return value


def _key(ref: dict):
    return (ref.get("handle"), ref.get("segment_index"), ref.get("layer"))


def _ref(ref: dict) -> str:
    return "handle {}, segment {} (zero-based), layer {}".format(
        _short(ref.get("handle", "?")), _short(ref.get("segment_index", "?")), _short(ref.get("layer", "?")))


def _location_rows(finding: dict) -> tuple[list[str], list[tuple], list[dict], bool]:
    """Only known rules get geographic markers; unknown findings stay visible."""
    detail = finding["details"]
    rule = finding["rule_id"]
    rows, points, refs = [], [], []
    shortened = False

    def row(text):
        nonlocal shortened
        if len(rows) < MAX_LOCATORS_PER_FINDING:
            rows.append(_short(text))
        else:
            shortened = True

    def point(value, label="coordinate"):
        if _point(value):
            row(f"{label}: ({value[0]}, {value[1]}) drawing units")
            if len(points) < MAX_LOCATORS_PER_FINDING:
                points.append(tuple(value))

    def reference(ref):
        if type(ref) is dict:
            row(_ref(ref))
            if len(refs) < MAX_LOCATORS_PER_FINDING:
                refs.append(ref)

    if rule in {"TOPO001", "TOPO002"}:
        nodes = detail.get("endpoints" if rule == "TOPO001" else "nodes", [])
        for node in nodes[:MAX_LOCATORS_PER_FINDING]:
            point(node.get("point"), "reported endpoint-graph representative")
            entities = node.get("entities", [])
            for ref in entities[:8]:
                reference(ref)
            shortened |= len(entities) > 8
        shortened |= len(nodes) > MAX_LOCATORS_PER_FINDING
    elif rule in {"TOPO003", "TOPO004"}:
        clusters = detail.get("clusters", [])
        for cluster in clusters[:MAX_LOCATORS_PER_FINDING]:
            for value in cluster[:8]:
                point(value, "reported cluster coordinate sample")
            shortened |= len(cluster) > 8
        shortened |= len(clusters) > MAX_LOCATORS_PER_FINDING
    elif rule in {"DUP001", "GEOM002", "INTER001", "INTER002", "INTER003"}:
        for key in ("start", "end", "point"):
            point(detail.get(key), "approximate crossing display" if key == "point" and detail.get("point_is_approximate") else key)
        for key in ("contact_points", "overlap_endpoints"):
            values = detail.get(key, [])
            for value in values[:MAX_LOCATORS_PER_FINDING]:
                point(value, key)
            shortened |= len(values) > MAX_LOCATORS_PER_FINDING
        entities = detail.get("segments", [])
        for ref in entities[:MAX_LOCATORS_PER_FINDING]:
            reference(ref)
        shortened |= len(entities) > MAX_LOCATORS_PER_FINDING
        if "entity" in detail:
            reference(detail["entity"])
    # Unsupported/metadata findings have textual CAD locators, never invented XY.
    for key in ("handle", "entity_type", "layer", "layout", "block", "entity_count",
                "declared_code", "expected_code", "failure", "reason", "phase"):
        if key in detail:
            row(f"{key}: {_short(detail[key])}")
    return rows, points[:MAX_LOCATORS_PER_FINDING], refs, shortened


CSS = """
:root{color-scheme:light;font-family:system-ui,sans-serif;color:#14232c;background:#eef2f4}
*{box-sizing:border-box}body{margin:0}header,main,footer{max-width:1240px;margin:auto;padding:24px}
header{padding-bottom:8px}h1{margin:0 0 12px;font-size:28px}h2{font-size:19px;margin:0 0 12px}
p{line-height:1.5}.warning{background:#fff0d5;border-left:5px solid #a65400;padding:14px;font-weight:650}
.meta{display:flex;gap:12px;flex-wrap:wrap}.pill{background:#dce4e8;padding:7px 12px;border-radius:5px}
.layout{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(320px,1fr);gap:20px;align-items:start}
.panel{background:white;border:1px solid #ced8df;border-radius:8px;padding:18px;min-width:0}
.plot{position:sticky;top:16px}.canvas{width:100%;height:auto;display:block;background:#f7fafb;border:1px solid #d5e0e5}
.base{stroke:#637b88;stroke-width:1.4;fill:none}.location{stroke:#bb350f;stroke-width:2.5;fill:none}
.marker{fill:white;stroke:#bb350f;stroke-width:2.5}.location:target .marker,.location:target line{stroke:#7d1dc4;stroke-width:4}
.location:target .marker{fill:#ead4ff}.issue:target{outline:3px solid #7d1dc4}.label{font-size:13px;fill:#8c280b;stroke:white;stroke-width:4;paint-order:stroke;stroke-linejoin:round}
.issue{border-top:1px solid #dce3e7;padding:14px 0;scroll-margin:16px}.issue:first-of-type{border-top:0}
.issue h3{font-size:16px;margin:0 0 6px}.issue p{margin:5px 0}.locators{font:12px/1.6 ui-monospace,monospace;padding-left:20px}
.small{font-size:13px;color:#425964}a{color:#21579d}ul{padding-left:20px}.break{overflow-wrap:anywhere}
.empty{padding:35px 10px;text-align:center}.checks{font:12px/1.7 ui-monospace,monospace}.legend{display:flex;gap:16px;flex-wrap:wrap}
@media(max-width:900px){.layout{grid-template-columns:1fr}.plot{position:static}header,main,footer{padding:16px}}
@media print{.plot{position:static}.layout{display:block}.panel{margin-bottom:12px}.issue{break-inside:avoid}}
"""


def render_html(report: dict, geometry: dict | None) -> str:
    """Render bounded SVG and locators; never reads a filename or external URL."""
    geometry = validate_geometry(geometry, report)
    segments = geometry["segments"] if geometry else []
    index = {_key(s): s for s in segments if not s["locator_shortened"]}
    cards, locations = [], []
    markers_left = MAX_DISPLAY_MARKERS
    for number, finding in enumerate(report["findings"][:MAX_DISPLAY_FINDINGS], 1):
        rows, points, refs, shortened = _location_rows(finding)
        highlighted = [index[_key(ref)] for ref in refs if _key(ref) in index]
        kept_points = points[:markers_left] if geometry else []
        markers_left -= len(kept_points)
        shortened |= len(kept_points) < len(points)
        # References locate only segments actually present in this bounded preview.
        if geometry and (kept_points or highlighted):
            locations.append((number, kept_points, highlighted))
            link = f'<a href="#loc-{number}">Locate #{number} in overview</a>'
        else:
            link = 'No plotted location; use the CAD locators below'
        cards.append(f'<article class="issue break" id="issue-{number}"><h3>#{number} [{_safe(finding["rule_id"])}] {_safe(finding["severity"].upper())}</h3>'
                     f'<p>{_safe(finding["message"])}</p><p class="small">{link}</p>'
                     '<ul class="locators">' + ''.join(f'<li>{escape(row)}</li>' for row in rows) + '</ul>'
                     + ('<p class="small">Display locators/markers are shortened. Full details remain in JSON.</p>' if shortened else '') + '</article>')

    all_points = [tuple(s[k]) for s in segments for k in ("start", "end")]
    all_points.extend(p for _, points, _ in locations for p in points)
    svg = '<div class="empty">No supported snapshot geometry available to draw</div>'
    if all_points:
        # Translate and scale exactly before float conversion: both ±1e308
        # extents and a subnormal X span at constant Y=1 remain representable.
        xmin = Fraction(min(p[0] for p in all_points))
        ymin = Fraction(min(p[1] for p in all_points))
        width = Fraction(max(p[0] for p in all_points)) - xmin
        height = Fraction(max(p[1] for p in all_points)) - ymin
        scale = max(width / 720, height / 500) or Fraction(1)
        xpad, ypad = (800 - float(width / scale)) / 2, (580 - float(height / scale)) / 2

        def xy(point):
            return (xpad + float((Fraction(point[0]) - xmin) / scale),
                    580 - (ypad + float((Fraction(point[1]) - ymin) / scale)))

        def line(segment):
            x1, y1 = xy(segment["start"])
            x2, y2 = xy(segment["end"])
            return f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}"/>'

        base = []
        for segment in segments:
            title = (_safe(_ref(segment)) + (' [locator shortened]' if segment["locator_shortened"] else '')
                     + '; start ' + _safe(tuple(segment["start"])) + '; end ' + _safe(tuple(segment["end"])) + ' drawing units')
            base.append(f'<g><title>{title}</title>{line(segment)}</g>')
        overlays = []
        for number, points, highlighted in locations:
            content = ''.join(line(segment) for segment in highlighted)
            for point in points:
                x, y = xy(point)
                content += f'<circle class="marker" cx="{x:.3f}" cy="{y:.3f}" r="6"/>'
            anchor = points[0] if points else highlighted[0]["start"]
            x, y = xy(anchor)
            content += f'<text class="label" x="{x + 9:.3f}" y="{y - 9:.3f}">#{number}</text>'
            overlays.append(f'<g class="location" id="loc-{number}"><a href="#issue-{number}"><title>Finding #{number}; open CAD locators</title>{content}</a></g>')
        svg = ('<svg class="canvas" viewBox="0 0 800 580" role="img" aria-labelledby="plot-title plot-desc" xmlns="http://www.w3.org/2000/svg">'
               '<title id="plot-title">Supported straight segment overview</title><desc id="plot-desc">WCS XY, Y upward. Numbered orange highlights refer to the findings list. This is a schematic overview, not a CAD rendering.</desc>'
               '<g class="base">' + ''.join(base) + '</g>' + ''.join(overlays) + '</svg>')

    total = report["summary"]["extracted_segments"]
    subset_note = f'Drawn {len(segments)} of {total} extracted supported segments; unsupported geometry is never drawn.'
    if total > len(segments):
        subset_note += f' Preview limited to the first {MAX_DISPLAY_SEGMENTS} segments. Omitted geometry may contain findings.'
    if geometry and not geometry["scan_complete"]:
        subset_note += ' Entity extraction stopped early; the unscanned remainder is unknown.'
    if geometry and any(s["locator_shortened"] for s in segments):
        subset_note += ' Overlong names are shortened and cannot be matched for segment highlights.'
    findings_note = f'Showing {min(len(report["findings"]), MAX_DISPLAY_FINDINGS)} of {len(report["findings"])} findings.'
    if len(report["findings"]) > MAX_DISPLAY_FINDINGS:
        findings_note += ' Additional findings are omitted from HTML; request JSON for full details.'
    counts = Counter(f["rule_id"] for f in report["findings"])
    rule_counts = ', '.join(f'{_safe(rule)}: {count}' for rule, count in sorted(counts.items())) or 'none'
    unit = report.get("units", {})
    unit_text = f'{_short(unit.get("name", "unavailable"))} ($INSUNITS={_short(unit.get("code", "unavailable"))})'
    integrity = report["input"]["unchanged_during_analysis"]
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            '<title>DXF Preflight | Offline inspection overview</title><style>' + CSS + '</style></head><body>'
            '<header><h1>DXF Preflight · inspection overview</h1>'
            '<p class="warning">MANUAL REVIEW REQUIRED · gate_eligible: false<br>This limited report never authorizes production. Unsupported content is omitted from the drawing, not cleared.</p>'
            f'<div class="meta"><span class="pill">Status: {_safe(report["status"])}</span><span class="pill">Declared units: {escape(unit_text)}</span>'
            f'<span class="pill">Tolerance: {_safe(report["parameters"]["endpoint_tolerance"])} drawing units</span></div>'
            f'<p class="small break">Input: {_safe(report["input"]["path"])}<br>Captured SHA-256: {_safe(report["input"]["sha256"] or "unavailable")}<br>'
            f'Final source bytes match capture: {_safe(integrity)}. Transient changes between reads can be missed.</p></header>'
            '<main><div class="layout"><section class="panel plot" id="overview"><h2>Supported snapshot geometry</h2>' + svg +
            '<p class="small legend"><span>Gray: extracted supported segments</span><span>Orange: numbered finding locations/references</span></p>'
            '<p class="small">All layers are overlaid. CAD visibility, colors and operation intent are not reproduced. Y points upward. SVG coordinates are scaled and rounded; close/short features can overlap visually. Endpoint-graph markers can be tolerance-cluster representatives; referenced segments keep their original endpoints. Cluster markers show reported coordinate samples, not snapped geometry. Crossing display points are approximate.</p>'
            f'<p class="small break">{escape(subset_note)}</p></section><section class="panel"><h2>Findings and CAD locators</h2>'
            f'<p class="small">{escape(findings_note)}</p><p class="small break">Rule totals: {rule_counts}</p>' +
            (''.join(cards) or '<p>No findings in the limited checks. This is not production approval.</p>') +
            '</section></div><section class="panel" style="margin-top:20px"><h2>Check states and limits</h2><div class="checks">' +
            '<br>'.join(f'{_safe(name)}: {_safe(state)}' for name, state in report["checks"].items()) + '</div>'
            '<p class="small">A check state of checked means executed within its declared population. Findings and overall status retain their original meaning. The preview does not add any checks. Display limits: 2,000 segments, 256 findings, 512 point markers, 24 locators per finding; strings longer than 256 characters are shortened; at most 64 not-checked entries are shown. Full report details remain in JSON.</p>'
            '<h2>Not checked</h2><ul>' + ''.join(f'<li>{_safe(item)}</li>' for item in report["not_checked"][:MAX_NOT_CHECKED_ITEMS]) + '</ul>' +
            ('<p class="small">Additional not-checked entries are omitted; see JSON.</p>' if len(report["not_checked"]) > MAX_NOT_CHECKED_ITEMS else '') + '</section></main>'
            f'<footer class="small break">{_safe(report["disclaimer"])}<p>Offline file · no scripts, network resources, uploads or repairs. Reports expose drawing metadata and geometry; keep them private.</p></footer></body></html>\n')
