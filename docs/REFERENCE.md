# Detailed geometry and resource reference

## Supported input and checks

- Regular DXF files up to 32 MiB, parsed by `ezdxf.readfile(errors="strict")`
- Modelspace `LINE` exactly in the WCS XY plane (`z=0`), zero thickness and
  default extrusion `(0,0,1)`
- Modelspace `LWPOLYLINE` with default extrusion, zero elevation, zero widths,
  zero thickness and **zero bulge at every vertex**, including its last vertex
- `$INSUNITS` declaration, optionally compared with `--expected-unit`
  (`in`, `ft`, `mm`, `cm`, `m`). Recognized other nonzero INSUNITS codes are
  reported without conversion. This is provider-neutral metadata checking,
  not a particular supplier's inch/mm-only policy
- Exact direction-normalized **segment** duplicates on the same layer,
  including LINE versus a straight polyline segment. Coordinates are not
  rounded. Layer names are case-insensitive. Color and linetype do not change
  this geometric comparison, so a duplicate finding is not a judgment about
  operation intent. Nothing is removed from the original drawing
  Entity and layer colors, true colors, linetypes and lineweights are retained
  alongside segment references. `operation_inferred` remains false; a coincident
  cut/etch path with different styles may be intentional, so no deletion is advised
- Layer-isolated endpoint graph: open-chain endpoints (degree 1), branch or
  shared endpoint nodes (degree >2), and degree-two cycle component counts
- Same-layer straight-segment interior crossings (including bow-tie
  self-intersections), exact endpoint-on-edge-interior contacts/T-junctions,
  and exact positive-length collinear overlaps. Legal shared/adjacent endpoints
  are not reported as crossings; exact duplicates remain a separate rule
- Zero/short segments at or below the endpoint tolerance are reported and
  excluded from topology. Exact duplicates are counted once in the analysis
  graph, so they cannot create a spurious closed two-edge contour

All modelspace geometry is inspected regardless of visibility, frozen state,
or layer style. Multiple layers produce a warning; no cut/engrave layer is
guessed or selected automatically. An open polyline that explicitly returns
to its first coordinate may form a geometric cycle even without the closed
flag. A closed flag alone is never treated as manufacturing approval.

Every unsupported modelspace entity, any non-layout block definition (even
empty/unreferenced), and any paperspace content produce an `incomplete` status.
This includes INSERT, ARC, CIRCLE, old POLYLINE, SPLINE, TEXT, DIMENSION and
HATCH. Blocks are not recursively expanded. Unsupported attributes are not
projected, approximated or silently discarded. Findings on supported geometry
remain visible when unsupported content is also present.

## Standalone CIRCLE/ARC measurements only

The first 256 standalone modelspace CIRCLE/ARC entities are considered for
analytic display measurements. Required entity attributes must be present;
ezdxf's defaults for absent center, radius or ARC angles are not accepted.
The center must be exactly `z=0`, with default `(0,0,1)` extrusion and zero
thickness. Reversed/tilted/nonunit extrusion, elevated/thick curves, block
contents and paperspace curves are not transformed or measured.

For eligible entities the report retains center, radius, CAD handle/layer/style,
length and XY bounds. ARC records also retain original and normalized angles,
counterclockwise sweep, and endpoints. Arc bounds use the endpoints and only
those cardinal extrema reached by that sweep; a wrapped 315-to-45-degree arc
does not get whole-circle bounds. The [ezdxf ARC definition](https://ezdxf.readthedocs.io/en/stable/dxfentities/arc.html)
specifies the counterclockwise direction around the extrusion vector; the
[CIRCLE definition](https://ezdxf.readthedocs.io/en/stable/dxfentities/circle.html)
specifies OCS center/radius semantics.

Derived length, endpoints and bounds are explicitly **approximate floating-point
display values**, not certified interval enclosures. Cardinal-angle inclusion
and angle normalization use exact fractions of the already parsed floats; no
precision lost during DXF parsing is recovered. Non-finite values, nonpositive
radius, overflow/underflow, unresolved radius at a large center, or collapsed
arc endpoints get no measurement. Equal normalized ARC angles are rejected
rather than inferred to mean a zero-length arc or a full circle. No endpoint
tolerance, unit conversion, snapping or tessellation is used for measurements.

`summary.curve_measurements.status` is checked only when the entity scan completed
and every encountered curve was measured, including the empty curve population.
Rejected/budget-skipped curves or a truncated scan make it unknown; already
measured records remain visible. A worker failure makes it unknown with no
invented measurements. An unreadable input leaves it not_run. The counts refer
only to the scanned curve population; they never claim the unscanned remainder.
The text report shows at most eight records; JSON retains up to 256.

**Every curve still emits SCOPE001 and remains outside the supported segment
population.** `supported_entities` retains its straight-segment meaning;
`unsupported_entities` includes measured curves. Curve duplicates, line/curve
or curve/curve contacts/intersections, endpoint connectivity and closed-contour
classification are all unchecked. A CIRCLE measurement does not add an endpoint
cycle; an ARC cannot close a line chain in this tool. No whole-drawing perimeter,
operation intent, manufacturing suitability or closed-curve count is reported.

## Tolerance and units

The default endpoint tolerance is `1e-6` **drawing units**, an absolute Euclidean
distance. Change it explicitly with `--tolerance`; it must be finite and >0.
The tool does not infer an appropriate manufacturing tolerance. Plane/OCS
membership and exact duplicate matching use exact values, not this tolerance.

Distinct endpoints within tolerance produce `TOPO003` warnings, including
their coordinates, rather than a silent clear report. Candidate matches use
neighboring spatial buckets, not rounded coordinates. A transitive proximity
chain whose cluster diameter exceeds tolerance produces `TOPO004` and leaves
that layer's topology unclassified. This avoids treating A~B and B~C as A~C.
Nearby separate contours may still be ambiguous; inspect all proximity warnings
in the original CAD drawing. The tool does not move any coordinate.

Segment-interior classification uses exact integer orientation predicates on
the **binary float values already parsed by ezdxf**. Binary coordinates are
scaled to a common power-of-two denominator, so nearly collinear inputs are
not guessed using a floating epsilon. Intersection points are approximate
display coordinates, clearly labeled in JSON; no coordinate is rewritten.
This does not recover precision already lost during DXF-to-float parsing,
infer physical accuracy, snap near-intersections, or merge operations. An
X-bounding-box sweep has an explicit global candidate-pair budget; resource,
report-count or exact-integer range exhaustion sets
`summary.segment_intersections.status` to `unknown` and makes the overall
report `incomplete`. A check never silently stops with a clear result.

Missing/unitless/unrecognized `$INSUNITS` produces `incomplete` even when an
expected unit is supplied. A mismatch is an error, and no 25.4 conversion or
other scaling is attempted. `$LUNITS` (display format), `$MEASUREMENT`
(hatch/linetype system), DIMENSION values and dimension text are not used to
infer physical length. A declared unit cannot prove intended 1:1 scale.
See the [official ezdxf units documentation](https://ezdxf.readthedocs.io/en/stable/concepts/units.html).
Malformed unit values with incorrect DXF tag types also remain incomplete.
Non-finite metadata is retained as safe text with `raw_value_type`, rather than
crashing JSON/text output or being accepted as a unit.

## Status and exit codes

| Status | Exit | Meaning |
| --- | ---: | --- |
| `limited_checks_clear` | 0 | No finding in the covered, explicitly limited checks |
| `issues_found` | 1 | Error or warning found; see findings |
| `incomplete` | 2 | Unsupported content, unresolved units, ambiguous tolerance, resource limit, or unstable input |
| `unreadable` | 3 | Not a readable regular DXF file; no recovery/audit attempted |
| report-write failure | 4 | Requested output could not be written |

Invalid CLI arguments also use argparse exit code 2. `incomplete` takes
precedence over known issues; those issues are still included in the report.
`coverage_complete_for_declared_subset` means only the above subset was
covered, never full drawing/manufacturing coverage. There is deliberately no
`pass`, `safe`, or `ready_to_cut` status.

The JSON schema is versioned as `1.1`; see [REPORT_CONTRACT.md](REPORT_CONTRACT.md) for its packaged schema and additive migration from 1.0. Reports contain the input SHA-256,
DXF version, tool/parser versions, parameters, unit source, counts, layers,
stable rule IDs, coordinates and entity handles. No timestamps are added,
so analyzing unchanged file bytes with the same version/options is repeatable.
A bounded input byte capture is hashed and parsed from a private temporary copy. The original path is read once more afterward and compared with that capture. This is an integrity check, not a security audit or a hostile-race
guarantee. Paths remain local unless you choose to share the report.

## Stable rule IDs

| Rule | Meaning |
| --- | --- |
| FILE001 | Unreadable/nonregular/malformed input |
| FILE002 | Input changed or could not be re-read for hash verification |
| UNIT001 | Missing, unitless or unrecognized INSUNITS |
| UNIT002 | Declared and explicitly expected units differ |
| SCOPE001 | Unsupported modelspace entity type |
| SCOPE002 | Non-XY/elevated/extruded/thick geometry |
| SCOPE003 | Polyline bulge |
| SCOPE004 | Polyline width or unknown flags |
| SCOPE005 | Block definition or paperspace content |
| SCOPE007 | Resource or numeric range limit |
| SCOPE008 | Entity attribute extraction failed |
| SCOPE009 | Worker start/crash/invalid result or an unconfirmed required check |
| GEOM001 | Non-finite geometry values |
| GEOM002 | Too few vertices, zero/short segment, nonpositive curve radius or equal normalized ARC angles |
| GEOM003 | No supported segments |
| DUP001 | Same-layer exact direction-normalized segment duplicate |
| TOPO001 | Degree-one endpoints / open chains |
| TOPO002 | Branch/shared endpoint nodes |
| TOPO003 | Distinct endpoints within tolerance; manual inspection needed |
| TOPO004 | Transitive tolerance ambiguity; topology incomplete |
| LAYER001 | Geometry spans multiple separately analyzed layers |
| INTER001 | Exact same-layer segment-interior crossing |
| INTER002 | Exact endpoint-on-other-segment-interior contact/T-junction |
| INTER003 | Exact positive-length same-layer collinear overlap |

## Important unchecked cases

Every report lists these limitations, even when its limited checks are clear:

- Cross-layer crossings/overlaps and cross-layer duplicate interpretation
- Near-intersections, line-on-edge tolerance snapping and near-duplicates
- Winding, nesting, islands/holes, bridge intent and minimum feature dimensions
- Intended scale, materials, stock thickness, process limits, kerf, tooling,
  heat effects, tolerances, fixture stability or machine/toolpath safety
- Full DXF structural validation and CAD display/plot semantics

The `self_crossing.dxf` bow-tie demonstrates why degree-two topology is
insufficient by itself: the segment-interior check now reports INTER001.
Independent review's two intersecting rectangles and triangle vertex touching
a rectangle edge now report INTER001 and INTER002 respectively. These cases
remain marked manual-review-required and gate-ineligible. This prototype is
still too limited to gate supplier uploads or production on its own.

## Resources and untrusted files

Limits: 32 MiB input, 20,000 scanned modelspace entities, 10,000 extracted
segments, 1,000,000 endpoint comparisons, 250,000 X-overlap segment-pair
candidates, 256 reported segment-interior findings, 256 attempted curve measurements, and 4,096-bit exact
coordinate integers. A large polyline is rejected
before segment expansion. Exceeding a limit produces `incomplete`, not clear.
The parser loads the file **before** entity/geometry limits apply. The CLI now supervises parsing and analysis in a fixed subprocess with a 30-second wall-clock deadline, configurable with `--timeout`. A timeout kills and reaps that direct worker and returns `incomplete`/SCOPE007. Worker start, crash or invalid result returns `incomplete`/SCOPE009. No rendering, HATCH tessellation, recovery or audit is invoked. There are **no OS-enforced memory/CPU limits and no security sandbox**. The in-process `analyze()` API has no wall deadline. Use small trusted drawings; untrusted input requires your own isolated environment with OS-level limits. Files can change between reads; do not concurrently modify them.

## Reproduce the local experiment

```sh
python scripts/generate_fixtures.py
PYTHONPATH=src python scripts/generate_reports.py
python -m pytest -q
```

All 19 included fixtures are original synthetic drawings, not factory/customer
samples. Actual JSON/text outputs are included in `reports/`; the compact
`reports/fixture_summary.json` lists source hashes, results and rule IDs.
Regenerating drawings changes library-generated document metadata and hashes;
regenerate reports afterward. Test count and execution evidence are recorded
in `VALIDATION.md`. Synthetic coverage is not market or production validation.
`scripts/generate_curve_fixtures.py` regenerates only the four curve examples;
`scripts/generate_fixtures.py` regenerates the original 15 straight/scope examples.
