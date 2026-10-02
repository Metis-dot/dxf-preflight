# DXF Preflight v0.2 experimental alpha

AI-developed experimental software by the dxf-preflight contributors.
Only limited, read-only 2D checks are provided; this is not production-safe
validation, a manufacturing approval, or a CAM/safety certificate.

A **local, read-only handoff check for small, straight-line 2D DXF contours**.
Run it before another person reviews an export: see declared units, exact
coincident segments, open endpoints and same-layer interior contacts, with CAD
entity handles and coordinates. Parsing is provided by [ezdxf](https://github.com/mozman/ezdxf).
All included drawings are original invented examples; no customer geometry is needed.

Standalone planar CIRCLE/ARC entities also get **measurement-only** radius,
length and XY bounds, plus ARC endpoints and counterclockwise sweep. These are
approximate display values in drawing units. Curves still make the report
incomplete because their duplicates, intersections and connectivity are unchecked.

**Every result requires manual CAD/CAM review. Exit 0 is only “limited checks
clear”, never permission to manufacture, submit to a supplier, or skip review.**
Reports always say `manual_review_required: true`, `gate_eligible: false`.
No repair, upload, telemetry, account, network analysis, or toolpath generation.

## Is my drawing eligible?

- Modelspace LINE exactly in WCS XY (`z=0`), default extrusion and no thickness
- Straight LWPOLYLINE, zero bulge/width/elevation/thickness, default extrusion
- Declared `$INSUNITS`; `--expected-unit` only compares it, never fills or scales it
- Small trusted local regular files, up to 32 MiB; geometry budgets also apply

**Any ARC, CIRCLE, INSERT, block definition (even unused), annotation, old
POLYLINE, SPLINE or paperspace content makes the report incomplete.** No curve
tessellation, block expansion or flattening is performed. Findings on the
supported subset remain visible. Do not change a drawing merely to obtain clear.
See [the exact scope and budgets](docs/REFERENCE.md).

Measurement-only curves must have an explicit center/radius (and ARC angles),
exact `z=0`, default extrusion and zero thickness. Missing required attributes,
invalid radius, equal normalized ARC angles, numeric overflow/coordinate collapse,
or the 256-curve measurement budget leave measurements unknown. No full-drawing
perimeter, closed-curve count or certification is inferred.

Try `dxf-preflight fixtures/curve_measurements.dxf --expected-unit mm` for a
rectangle with an independently measured circle and arc. Exit 2 is expected;
the straight rectangle's endpoint cycle does not classify either curve.

## Install locally

Trial support verified: **Python 3.12.14 on Linux x86_64**. Package metadata is
limited to Python 3.12. Other Python versions and macOS/Windows are unverified.
Dependencies download from official PyPI during installation; analysis itself
uses no network calls. Use a new venv that does not inherit system packages.

POSIX, from the unpacked source folder:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/dxf-preflight --version
```

PowerShell invocation reference (not yet platform-validated):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\dxf-preflight.exe --version
```

An existing locally built wheel can instead be installed with
`python -m pip install /path/to/dxf_preflight_prototype-0.2.0-py3-none-any.whl`.
Source is available at [Metis-dot/dxf-preflight](https://github.com/Metis-dot/dxf-preflight).
No PyPI package or formal GitHub release is published. Keep dependency notices;
see [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).

## 60-second demo

Run these four commands independently from the source folder. Nonzero exits
are expected, so do not join them with `&&` or enable “stop on any nonzero”.
On PowerShell replace `.venv/bin/dxf-preflight` with
`.\.venv\Scripts\dxf-preflight.exe`; `$LASTEXITCODE` shows each exit.

```sh
.venv/bin/dxf-preflight fixtures/rectangle_lines.dxf --expected-unit mm
.venv/bin/dxf-preflight fixtures/open_chain.dxf --expected-unit mm
.venv/bin/dxf-preflight fixtures/duplicate_reverse.dxf --expected-unit mm
.venv/bin/dxf-preflight fixtures/unsupported_arc.dxf --expected-unit mm
```

1. Rectangle: exit 0, `limited_checks_clear`, no limited-scope findings
2. Open chain: exit 1, `TOPO001`, endpoints `[0, 0]` and `[0, 20]`
3. Reversed duplicate: exit 1, `DUP001`; coincidence does not establish operation intent
4. Rectangle plus ARC: exit 2, `SCOPE001`; unsupported content prevents clear

For the open chain the text report identifies handle `2F`, segment indices 0
and 2 (zero-based), layer `0`, and the two endpoint coordinates. Locate those
entities/vertices in CAD and review whether the opening is intended. Handles
refer to the exact unchanged DXF export, not an edited copy. No deletion,
closing, snapping, or operation selection is advised.

Write both reports beside an exact export:

```sh
mkdir -p local-reports
.venv/bin/dxf-preflight fixtures/open_chain.dxf --expected-unit mm \
  --json-report local-reports/open.json --text-report local-reports/open.txt \
  --html-report local-reports/open.html
```

This exits 1 while writing all three reports. Open `open.html` in a local browser
for a numbered SVG overview and CAD locators. The file works offline with no
scripts or external assets. The preview adds no checks; unsupported geometry
is never drawn. See [visual scope, limits and privacy](docs/VISUAL_REPORT.md).
Parent folders must exist. Each report
is replaced atomically, but multiple reports are **not one atomic transaction**;
exit 4 names any report already written. Input aliases and colliding report
paths are rejected, including symlinks/hardlinks. Avoid concurrent path changes.
The report hash identifies the exact captured bytes that ezdxf parsed from a private temporary copy. The original source is read again afterward and compared with that capture; analysis never saves the original DXF. Only the bytes at checked read points are compared; transient changes between reads can be missed. This is not an atomic snapshot, hostile-race or security guarantee.

## Status and exit meaning

| Status | Exit | Interpretation |
| --- | ---: | --- |
| `limited_checks_clear` | 0 | All declared limited checks completed without findings |
| `issues_found` | 1 | Error/warning present; inspect references and intent in CAD |
| `incomplete` | 2 | Unsupported/unknown content, units, ambiguity or resource/worker failure |
| `unreadable` | 3 | No readable regular DXF; no recovery/audit was attempted |
| report-write failure | 4 | Requested output failed; stderr states any partial success |

Invalid CLI arguments also use argparse exit 2. Overall incomplete takes
precedence over known issues; those findings remain. “Coverage” only means
coverage of the declared subset, never the whole CAD/manufacturing workflow.
The complete [rule and fixture guide](docs/RULES.md) explains stable rule IDs.

## JSON contract and time boundary

`--format json` prints parseable UTF-8 JSON to stdout. The packaged
[JSON Schema 1.1](src/dxf_preflight/report.schema.json) includes explicit
`checked`, `not_run`, `unknown` states for each check. Schema 1.1 preserves 1.0
fields and adds `checks` and `execution`; see [migration and semantics](docs/REPORT_CONTRACT.md).
Findings include coordinates, layer names, handles and style metadata.
A valid schema is not a safety certificate.

The CLI runs its fixed parser/analysis worker with a **30-second wall-clock
limit**; use `--timeout SECONDS` to change it. A terminated/crashed/invalid
worker returns incomplete with unconfirmed checks; it never falls back to
clear. Timeout/crash reports retain the worker’s initial captured-input hash when available,
but leave `unchanged_during_analysis` null because no completed integrity result exists. A deadline before hashing completes has no hash.

**This is a time boundary, not a sandbox. No hard memory/CPU limit is applied.**
Input capture/hash, private snapshot parsing and analysis all run inside that worker deadline. Parent path validation, result/schema validation and report writing are outside it.
Use small trusted drawings; untrusted inputs need your own isolated environment
and OS limits. Direct Python `analyze(path, *, tolerance, expected_unit)` keeps
its existing in-process behavior and has no deadline.

## Reproduce and report problems safely

```sh
.venv/bin/python -m pip install -c constraints-dev.txt '.[test]'
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src scripts tests
```

See [VALIDATION.md](VALIDATION.md) for actually executed checks, clean wheel
installation evidence and unverified stages. Original DXF fixtures and their
actual deterministic JSON/text reports are included. Fixture regeneration
changes ezdxf document metadata/hashes, so regenerate reports afterward.

Use the [feedback template](docs/FEEDBACK.md) with a minimal invented reproduction.
**Do not share customer drawings or real reports**: reports expose paths,
layer names, coordinates and styles. Removing a filename is not anonymization.
Repository issues can be used for invented reproductions only. No tester
outreach or hosted service has been created.
Synthetic tests do not demonstrate factory acceptance, customer demand or
willingness to pay. This is a deliberately narrow developer trial.

## License

Original project code, documentation and synthetic fixtures are available under
the [MIT License](LICENSE). Separately installed dependencies keep their own
licenses and notices; the project license does not replace those licenses.
See [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).

[VALIDATION.md](VALIDATION.md) records the pre-publication synthetic checkpoint.
It does not establish real factory acceptance, production safety or demand.
