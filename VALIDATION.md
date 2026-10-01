# v0.2 trial validation record

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
