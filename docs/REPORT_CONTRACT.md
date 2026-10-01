# Report contract 1.1

The checked-in schema is `src/dxf_preflight/report.schema.json`, included in
both source and wheel. It uses JSON Schema Draft 2020-12 without a remote
project `$id`; validation can run entirely offline after installing jsonschema.
Read it from an installed wheel with `importlib.resources.files("dxf_preflight").joinpath("report.schema.json")`.

## Migration from 1.0

Version 1.1 is additive: existing `analyze()` arguments, overall status names,
exit meanings, findings/details, summary counters, input hash and conservative
review fields remain. New top-level `checks` and `execution` expose completed
work and the CLI boundary. `summary.segment_intersections.status` retains
`checked` / `not_run` / `unknown`; legacy layer summaries retain `checked` /
`incomplete`. A truncated entity scan now marks downstream coverage unknown,
even if known findings on the inspected prefix are available.

Consumers should dispatch on `schema_version`, accept additive fields, preserve
unknown findings, and fail closed on unknown versions/statuses. Do not equate
an empty findings array, `checked`, a degree-two cycle, or declared units with
production approval. Stable rule IDs are described in [RULES.md](RULES.md).
A changed meaning or removed field requires a future major schema version.

## Individual check states

- `checked`: the named check completed on its declared population. It can find
  invalid units or geometry; checked means executed, not acceptable
- `not_run`: the check was not entered, for example geometry after an unreadable
  file or segment budget failure
- `unknown`: execution/coverage could not be confirmed, such as parse failure,
  skipped entity remainder, unsupported extraction, topology ambiguity or a
  killed/crashed worker

Checks are `input_read`, `parsing`, `units`, `scope`, `segment_extraction`,
`duplicates`, `topology`, `segment_intersections`, `input_integrity`. Duplicate,
topology and intersection checks refer to supported, nondegenerate, same-layer
segments only. Unsupported content makes extraction unknown and overall status
incomplete even when checks on supported geometry completed. Empty/all-short
geometry keeps GEOM002/GEOM003; vacuous subset work does not make it clear.

All checks must be checked, the input verified unchanged, and findings empty
before `limited_checks_clear` can be produced. Overall `incomplete` takes
precedence over known error/warning findings. Unreadable takes precedence for
input-reading/parsing failure. Known findings remain in the output.

## Execution and integrity

Direct API reports have `execution.mode: in_process`, no wall deadline.
CLI reports have `mode: subprocess` and a positive deadline in seconds. Every
report says `hard_memory_limit: false`, `hard_cpu_limit: false`, `sandboxed: false`.
The fixed local worker runs no user-provided code. A worker failure yields
SCOPE007 (deadline) or SCOPE009 (start/crash/invalid result), unknown unconfirmed
checks, no fabricated geometry findings, and null stable-snapshot verification.
The direct worker is killed and reaped on deadline; its parent-owned temporary directory is removed even after timeout/crash. This covers the direct worker,
not hypothetical descendants, OS memory/CPU containment or parent I/O time.

Normal completed reports parse a private temporary copy of one bounded byte capture. Its SHA identifies the exact parsed bytes. The original path is read again at the end and compared with that capture. Timeout
reports retain the bounded initial worker SHA when possible. That hash identifies
bytes observed by the worker before parsing, not geometry successfully analyzed. A timeout before the hash record completes leaves it null. Missing,
nonregular or over-size input may have no hash. No timestamp is added, so the
same exact bytes/path/options/tool version yield deterministic reports.
The comparison only covers bytes at checked read points. Transient changes between the separate reads can be missed; this is not an atomic byte snapshot. Input/output path races are not securely isolated; keep the file and paths stable.

Tolerance is absolute Euclidean distance in drawing units, not millimeters by
assumption. Intersection display points are approximate, marked as such; the
predicate operates exactly on floats already parsed by ezdxf. No scaling or
coordinate rewriting is performed. Full style metadata stays in JSON even
when text displays compact locators/representative unsupported handles.

## Validation boundaries

Schema checks report structure and conservative constants; tests also compare
actual severity totals, known fixture outcomes and check-state consistency.
Some rule-specific `details` remain extensible objects to preserve existing
metadata and permit future locators. Schema validity is not mathematical proof,
complete parser fuzzing, malicious-input safety or manufacturing validation.
