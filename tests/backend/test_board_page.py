import shutil
import subprocess
from pathlib import Path

import pytest

UI = Path(__file__).parents[2] / "src/frontend"


@pytest.mark.skipif(not (UI / "node_modules").exists() or not shutil.which("npx"), reason="needs `npm install` in src/frontend")
def test_board_app_typechecks():
    """One type error (say, a misspelled field from /api/board) can blank the whole board, and no Python test would notice."""
    result = subprocess.run(["npx", "tsc", "--noEmit"], cwd=UI, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
