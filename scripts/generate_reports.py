"""Run the real analyzer against each included synthetic fixture."""

import json
from pathlib import Path

from dxf_preflight import analyze
from dxf_preflight.cli import render_text

ROOT = Path(__file__).resolve().parents[1]


def generate():
    summary = []
    for path in sorted((ROOT / "fixtures").glob("*.dxf")):
        report = analyze(path, expected_unit="mm")
        report["input"]["path"] = str(path.relative_to(ROOT))
        output = ROOT / "reports" / path.stem
        json_text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        output.with_suffix(".json").write_text(json_text, encoding="utf-8")
        # Render the persisted JSON representation: its sorted dictionary order
        # is also what the CLI worker transport returns, not API insertion order.
        output.with_suffix(".txt").write_text(render_text(json.loads(json_text)), encoding="utf-8")
        summary.append({"fixture": path.name, "status": report["status"], "rule_ids": sorted({f["rule_id"] for f in report["findings"]}), "sha256": report["input"]["sha256"]})
    (ROOT / "reports" / "fixture_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for item in summary:
        print(f"{item['fixture']}: {item['status']} {','.join(item['rule_ids']) or '(no findings in the limited checks)'}")


if __name__ == "__main__":
    generate()
