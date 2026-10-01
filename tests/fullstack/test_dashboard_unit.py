"""Runs the dashboard's JavaScript unit tests (dashboard/tests, node:test) as part of the Python suite."""
import shutil
import subprocess
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parents[2] / "dashboard" / "tests"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_dashboard_js_unit_tests_pass():
    files = sorted(str(p) for p in TESTS.glob("*.test.mjs"))
    assert files
    r = subprocess.run(["node", "--test", *files], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
