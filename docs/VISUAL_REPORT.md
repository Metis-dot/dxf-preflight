# Offline visual inspection overview

`--html-report PATH` writes a self-contained HTML file with a bounded SVG
preview of **accepted modelspace straight LINE / LWPOLYLINE segments only**.
It uses the original analysis worker's captured and hashed input, not a second
DXF parse. Input integrity, all analysis findings/statuses, review requirements,
JSON schema 1.1 and exit meanings stay unchanged for completed checks. Opt-in display capture/serialization adds worker work and can affect whether a tight deadline is reached. No display data is added to
JSON or to the existing `analyze()` API result.

```sh
.venv/bin/dxf-preflight fixtures/open_chain.dxf --expected-unit mm \
  --html-report local-reports/open.html --json-report local-reports/open.json
```

Parent folders must exist. The open chain exits 1 while writing the reports.
Open the HTML file in a local browser. It needs no server, JavaScript, internet,
fonts, images, file picker, upload or external resource. Numbered finding links
select orange locations/referenced segments; clicking a plotted finding returns
to its CAD locators. Selected SVG locations are highlighted in purple. Browser
zoom and print can help; no CAD pan/zoom/measurement tool is provided.

## How to read the drawing

- Gray segments are original accepted straight geometry before duplicate or
  short-segment omission from topology. Their coordinates have not been repaired
- Orange numbered highlights are known finding points and/or referenced
  segments present in the preview. All layers are overlaid. Visibility, plot
  styling, operation intent and CAD display semantics are not reproduced
- SVG is a normalized WCS XY overview with Y upward. Normalization is computed
  before rounded SVG coordinate display, including huge or subnormal spans.
  Very close/short features may still overlap visually; the plot is not a
  measurement or scale/physical-size assertion
- TOPO001/TOPO002 points are reported endpoint-graph representatives. A
  referenced segment's endpoint may be within tolerance rather than equal to
  that point. Segment coordinates remain original; no gap-closing edge is drawn
- TOPO003/TOPO004 markers show reported coordinate samples. Ambiguous cluster
  findings already contain at most eight coordinates per cluster; these are
  not complete reconstructed clusters or repaired/snap locations
- INTER001 crossing display coordinates are approximate; textual labels retain
  that distinction. Unsupported geometry and metadata/worker findings do not
  get invented XY locations. Use their handles/layers/details in CAD/JSON

**An incomplete report can show supported geometry and known findings while
remaining incomplete. Omitted ARC, INSERT, block, bulge, width, 3D or other
unsupported geometry is not cleared. Every status requires manual CAD/CAM
review; `gate_eligible` remains false. The preview adds no manufacturing checks.**

## Display limits

Display caps do not alter analysis budgets, checks, statuses or exit codes:

| Item | HTML limit |
| --- | ---: |
| Extracted segments | First 2,000 |
| Findings | First 256, retaining original finding numbers |
| Point markers | 512 globally, at most 24 per finding |
| Locator rows/referenced segment matches | At most 24 per finding |
| Name/message/metadata strings | 256 characters, with shortening disclosure |
| Not-checked entries | First 64 |

The page states displayed versus extracted segments, displayed versus total
findings, all rule totals, incomplete entity scanning and locator/marker
omissions. Full details remain in JSON when requested. Overlong handle/layer
names are shortened in segment titles and are not matched for named segment
highlights, preventing collisions between shortened locators. A known point
can still locate by its original reported coordinate.

A timed-out/crashed/invalid worker provides no display geometry and remains
incomplete. Malformed, oversized, mismatched-hash/count or non-finite display
payloads fail closed; they cannot supply an apparently completed preview.

Each requested report is atomically replaced independently. Multiple reports
are not an atomic transaction; exit 4 names those already written. HTML paths
receive the same input/output alias checks as JSON and text, including all
three-output pairs. Stable trusted source/output paths are still required;
this is not a hostile-path/race security guarantee or sandbox. Display capture runs within the existing worker deadline; parent-side validation, HTML rendering and report writing are outside it. Display caps are not a hard memory/CPU bound or total-CLI time promise.

## Privacy and examples

HTML exposes paths, captured hashes, coordinates, layer names, CAD handles and
finding information. Escaping metadata and using fixed internal fragment IDs
prevents it from becoming HTML/SVG markup; this is not an anonymization claim.
Keep real drawings and reports private. No transmission is performed.

Use `fixtures/open_chain.dxf`, `fixtures/self_crossing.dxf` and
`fixtures/unsupported_arc.dxf` to generate local HTML examples with
`--html-report`. These original invented fixtures show an open chain,
approximate crossing display and an incomplete supported rectangle with an
omitted ARC respectively. Generated reports are local artifacts and are not
included in this change. They are never production approval.
