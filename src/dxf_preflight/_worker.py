"""Fixed local analysis worker. No repair, shell execution, or network calls."""

import json
import sys

from .core import _analyze


def _emit(record: dict) -> None:
    # One compact record per line; embedded newlines/path separators are escaped.
    sys.stdout.write(json.dumps(record, ensure_ascii=True, sort_keys=True, allow_nan=False) + '\n')
    sys.stdout.flush()


def main() -> None:
    request = json.loads(sys.stdin.read())
    emitted = False

    def snapshot(digest):
        nonlocal emitted
        _emit({'kind': 'snapshot', 'path': request['path'], 'sha256': digest})
        emitted = True

    geometry = None

    def capture(value):
        nonlocal geometry
        geometry = value

    include_geometry = request.get("include_geometry", False)
    report = _analyze(request['path'], tolerance=request['tolerance'], expected_unit=request['expected_unit'], _on_snapshot=snapshot, _on_geometry=capture if include_geometry else None)
    if not emitted:
        snapshot(None)
    final = {'kind': 'report', 'report': report}
    if include_geometry:
        final['geometry'] = geometry
    _emit(final)


if __name__ == '__main__':
    main()
