"""CLI entry point for a bounded regional NDVI pilot run."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.regional_monitor import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
