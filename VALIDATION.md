# v0.2 trial validation record

## Local measurement-only development checkpoint, 2026-10-02 UTC

This increment is based on public main `21b1824`, separately from the offline
HTML-report branch. It retains package version 0.2.0 and additive schema 1.1
while awaiting review; it is not a new release or manufacturing approval.
Only original invented geometry was used, with no customer files.

- Unchanged main baseline: **189 passed in 12.65 seconds**
- Final development source suite: **277 passed** (including 84 new curve tests
  and four additional fixture-validation cases)
- `compileall -q src scripts tests` and `git diff --check`: passed
- Wheel built locally with build 1.3.0, setuptools 80.9.0, wheel 0.45.1
- The wheel was installed into an independent temporary target with `--no-index
  --no-deps`; the smoke run reused existing pinned dependencies from the earlier
  isolated venv. This was not a fresh dependency-resolution/platform trial
- Installed import was verified to resolve inside that target, outside this
  source checkout. All **19 fixtures** through its console entrypoint validated
  against the packaged schema, with expected statuses/exits, correct source
  hashes and exact source bytes unchanged after analysis
- Installed module entrypoint and requested JSON/text reports agreed for the
  mixed circle/arc example. `pip check` found no broken requirements
- A separate independent review ran 5,000 analytic/cardinal/wrapped-angle probes
  and checked rejected transforms, budgets, partial scans and style failures
- That review found parser defaults for absent required attributes could invent
  measurements. Explicit presence checks fixed it; raw missing center-x,
  center-y, radius and ARC-angle tags now have regression coverage. Missing
  optional center-z remains valid zero; strict parsing rejects absent center-y

The new tests cover translated circles, all quadrants, major/wrapped/negative
and very large finite ARC angles, noncardinal extrema, deterministic dense
sampling, non-finite/invalid radii, degenerate/equal angles, numeric overflow,
underflow and coordinate collapse, exact plane/OCS/thickness rejection, no unit
scaling, original-file preservation, missing required attributes, budget/scan
coverage, worker failure, schema/transport contradictions and capped text output.
Measurements never enter the straight-segment duplicate/intersection/endpoint
graph. Every curve keeps SCOPE001/incomplete, manual review required, gate false.

Bounds/endpoints/lengths are approximate display values, not interval-certified
enclosures. No curve intersections/duplicates, mixed connectivity, closed-curve
counts, whole-drawing perimeter or CAD interoperability/manufacturing trial was
added. The prior time boundary, path guards and lack of an OS security sandbox
are unchanged. No browser validation is involved in this JSON/text increment.

The original v0.2 evidence below is historical and covers the earlier 15-fixture
checkpoint; its curve limitations refer to that earlier implementation.

Executed on 2026-10-01 UTC using **only original synthetic DXF fixtures**.
This is a local, unpublished checkpoint, not factory/customer/supplier,
malicious-input, security-sandbox, performance-SLA or market validation.
No remote repository, public package, hosted service, project license or
public issue tracker was created or selected.

## Verified environment and installation

- Linux x86_64, Python **3.12.14**
- Package **0.2.0**, report schema **1.1**
- ezdxf **1.4.4**, jsonschema **4.25.1**, pytest **8.4.2**
- Build tools: build **1.3.0**, setuptools **80.9.0**, wheel **0.45.1**
- Fresh build and install venvs both had `include-system-site-packages = false`
- Dependencies were downloaded from the **official PyPI index**; validation
  versions, including transitive packages, are pinned in `constraints-dev.txt`
- Wheel built with the pinned tools and installed into the second fresh venv
- Installed checks ran from an independent temporary directory with
  `PYTHONPATH` removed, not an editable checkout; import resolved to that
  venv's `site-packages`
- `pip check` passed in both environments
- Metadata support narrowed to Python 3.12 (`>=3.12,<3.13`); no other Python or
  macOS/Windows compatibility is claimed. PowerShell examples are unverified

## Actual results

- Original v0.1 baseline: **119 tests passed**
- Final v0.2 source suite: **189 passed in 14.16 seconds**
- `compileall -q src scripts tests`: passed
- Final source ZIP extracted into an independent temporary directory:
  **189 passed** and compileall passed
- Installed console `--version` returned **0.2.0** and `--help` included the
  time boundary and manual-review warning
- Installed packaged schema loaded through `importlib.resources` and passed
  JSON Schema Draft 2020-12 meta-validation
- All **15 fixtures** through the installed console JSON entrypoint validated
  against the schema; reported input hashes matched the original fixture bytes
  and those source bytes were unchanged after execution
- Four-command text demo and module JSON entrypoint gave expected exits
  **0 / 1 / 1 / 2** for rectangle/open-chain/duplicate/unsupported-ARC
- Unicode, spaces and U+2028 in the installed input path worked; JSON stdout
  and requested JSON/text reports agreed
- Missing input: exit 3 / unreadable / valid schema
- Deadline before input hashing completed: exit 2 / incomplete / null hash
  and null `unchanged_during_analysis`, never clear
- Installed stdout remained parseable JSON, including expected nonzero exits

The environment can print an ezdxf cache-directory warning to stderr. No
permissions were changed to suppress it. JSON stdout remained uncontaminated.
The program performs no network requests during analysis.

## Conservative contract and failure paths verified

The original API signature remains:
`analyze(path, *, tolerance=1e-6, expected_unit=None)`. It runs in-process
without a deadline. Existing fields/rule results are preserved; schema 1.1
adds individual `checks` and `execution` fields. Every status retains
`read_only: true`, `manual_review_required: true`, `gate_eligible: false`.

New and retained tests cover:

- Clear/issues/incomplete/unreadable, malformed unit metadata and resource
  reports; all 15 actual saved fixture reports validate against the schema
- Explicit checked/not_run/unknown states, unknown topology for ambiguous
  tolerance clusters, and unknown downstream coverage for a truncated scan
- Clear reports with missing required fields, mismatched check/summary states,
  bad counts, false coverage, wrong path/options or relaxed review constants
  rejected by schema and/or the runtime semantic validator
- Worker startup failure, nonzero exit, missing/noisy/truncated JSON, deep JSON
  recursion and controlled hangs yield incomplete/SCOPE007 or SCOPE009
- Input capture/hash is inside the worker's wall-clock deadline; no completed
  hash produces null, while a complete initial hash record survives later
  invalid UTF-8 transport on timeout
- A controlled hung direct worker is killed and reaped; its parent-owned
  private temporary directory is removed after timeout
- One bounded byte capture is hashed and parsed by ezdxf from a private
  temporary copy. A regression temporarily swaps the original source before
  parser entry and restores it afterward: parsing still reflects the exact
  report-hashed captured bytes, rather than the swapped source
- Original-path changes visible at the final read yield FILE002/incomplete
- Unreadable reports remain deterministic; parser reasons do not expose a
  random private snapshot filename
- Unicode/space paths, report replacement, input/report symlink/hardlink
  aliases, report collisions created during analysis, self-referential output
  symlinks, controlled permission failure and temporary-output cleanup
- Two-output partial success names the already-written report on exit 4;
  there is no claim of a multi-file atomic transaction
- Compact text locators show open ends and zero-based segment indices;
  unsupported summaries state representative-handle counts while JSON keeps
  every finding and style/operation context
- Existing exact-dyadic segment crossings, contacts and overlaps, unit checks,
  geometry/count/range budgets, no-mutation and repeatability cases retained

Additional independent regression probes checked transport/path/schema
boundaries, installed entrypoints/resources, temporary-directory cleanup,
API signature and captured-byte integrity. They confirmed the final code's
conservative outcomes; they are not a complete adversarial test campaign.

## Reproduction commands

From the unpacked source (use a fresh Python 3.12 venv):

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --index-url https://pypi.org/simple \
  -c constraints-dev.txt 'build==1.3.0' 'setuptools==80.9.0' 'wheel==0.45.1' '.[test]'
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src scripts tests
.venv/bin/python -m build --no-isolation --wheel
```

Install the resulting wheel into a second venv without system packages, remove
`PYTHONPATH`, change to a different directory, and run the four original demo
fixtures plus both console/module entrypoints. Fixture hashes and known rule
IDs are in `reports/fixture_summary.json`. Tests intentionally make their
source-checkout worker path explicit; the clean wheel checks did not use it.

## Remaining boundaries

- The default 30-second deadline covers the fixed direct worker's input capture,
  hashing, private snapshot parsing and analysis. Parent path validation,
  schema/result validation, report writing and OS process-start/cleanup time
  are outside it. It is not a promise that all CLI wall time is capped
- No hard OS memory/CPU limit, security sandbox, process-tree containment,
  complete DXF structural audit, hostile-path isolation, parser fuzz campaign
  or real-world CAD interoperability test was performed
- The final original-path read only compares then-observed bytes with the
  captured input. Transient source changes between read points may go unseen;
  it does not prove the original file stayed unchanged throughout the run
- Preserve a stable source/path while running. Use small trusted drawings;
  untrusted files require a separate isolated environment with OS limits
- Curves, blocks, annotation, paperspace, cross-layer intersections, winding,
  nesting, dimensions/scale intent, kerf/material/process/toolpath safety and
  supplier acceptance remain outside scope. No automatic repair was added
- Dependency notices are retained; transitive dependencies are installed
  separately, not bundled. No full redistribution license audit was performed
- No real customer geometry, private engineering IP, user interviews,
  willingness-to-pay evidence or production approval exists in this checkpoint

## Offline HTML preview checkpoint (experimental feature)

Executed on 2026-10-01 UTC on Python 3.12.14 / Linux x86_64, against the same
original invented fixtures. This section records the local visual-report patch
and supersedes the 189-test total for this checkout only.

- Final source suite: **263 passed in 16.73 seconds** (189 retained + 74 new)
- `compileall -q src scripts tests` and `git diff --check`: passed
- Pinned build tools produced wheel and sdist successfully; the wheel includes
  `visual.py`, and the sdist includes visual docs and tests. Three local HTML
  examples were generated and checked separately; generated reports are not
  included in the draft feature change
- Project wheel newly installed into a fresh venv with system packages disabled,
  without editable/source installation. Pinned dependency files were copied
  from the earlier validated isolated install, not downloaded/reinstalled.
  `pip check` passed; installed imports resolved to the new venv's site-packages
- Installed console ran all 15 fixtures from an independent directory with
  `PYTHONPATH` removed. HTML and no-HTML runs had identical JSON stdout and
  exit codes; JSON validated against schema 1.1, source hashes matched and
  original bytes were unchanged. Installed module missing-input/HTML run
  returned exit 3 / unreadable with no fabricated display geometry
- Independent review verified all 15 fixture renderings, one captured source
  parse, escaped hostile metadata, bounded display output, huge and subnormal
  coordinate normalization, and malformed-display fail-closed behavior
- Structural HTML/SVG and fragment-ID tests passed. **Browser visual/rendering,
  responsive layout, actual fragment-click behavior and print QA were not
  completed**: local Chromium could not create sockets in this executor, and
  the cloud browser's URL policy rejected local file URLs. No policy bypass
  or external report publication was attempted

New regressions cover input/report aliases across three outputs; partial-write
exit 4; timeout/unreadable/incomplete display absence or qualified subset
previews; geometry capture from the same hashed snapshot; preserved JSON/text
and API results; known geographic locators versus unsupported/unknown findings;
shortened metadata and omitted marker/finding/segment/not-checked entries;
finite SVG output for enormous, narrow, subnormal and zero-size extents; hostile
HTML/SVG metadata; mismatched/malformed/oversized display transport; and integer
or JSON-exponent overflow rejected fail-closed. Rejecting `1e999` in worker
JSON also closes a pre-existing invalid-result serialization crash path.

Display caps do not provide a hard memory/CPU limit or a total-CLI wall deadline.
Opt-in capture/serialization adds worker work inside the existing deadline.
Parent validation, HTML rendering and output writing remain outside it. Normal
report analysis budgets and conservative/manual-review meaning are unchanged.
