"""Source-checkout tests intentionally give the CLI worker the same source tree.

Wheel smoke validation separately removes PYTHONPATH outside the checkout.
"""

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def source_worker_path(monkeypatch):
    source = str(Path(__file__).parents[1] / 'src')
    previous = os.environ.get('PYTHONPATH')
    monkeypatch.setenv('PYTHONPATH', source + (os.pathsep + previous if previous else ''))
