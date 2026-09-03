"""Ensure the project root is importable when running pytest.

Makes ``import app...`` work regardless of the current working directory,
fixing the ModuleNotFoundError that occurred when running test files directly
from app/tests/.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
