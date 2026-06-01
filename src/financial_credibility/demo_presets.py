"""Demo preset loading for reproducible CLI and web reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import UserFacingError


DEMO_PRESETS = {
    "equity_supported": "demo_equity_supported.json",
    "human_review": "demo_human_review.json",
    "mixed_assets": "demo_mixed_assets.json",
}


def available_demo_presets() -> list[str]:
    """Return stable preset names for CLI help and validation."""
    return sorted(DEMO_PRESETS)


def load_demo_preset(name: str | None) -> list[dict[str, Any]] | None:
    """Load prefetched evidence for a named deterministic demo preset."""
    if not name:
        return None
    key = str(name).strip().lower().replace("-", "_")
    filename = DEMO_PRESETS.get(key)
    if not filename:
        raise UserFacingError(
            "unknown_demo_preset",
            f"Unknown demo preset: {name}",
            f"Use one of: {', '.join(available_demo_presets())}.",
        )
    path = _examples_dir() / filename
    if not path.exists():
        raise UserFacingError(
            "demo_preset_not_found",
            f"Demo preset file was not found: {path}",
            "Restore the examples directory or provide --prefetched-json explicitly.",
        )
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_demo_preset(name: str | None) -> str | None:
    """Normalize a user-supplied preset name without loading it."""
    if not name:
        return None
    key = str(name).strip().lower().replace("-", "_")
    if key not in DEMO_PRESETS:
        raise UserFacingError(
            "unknown_demo_preset",
            f"Unknown demo preset: {name}",
            f"Use one of: {', '.join(available_demo_presets())}.",
        )
    return key


def _examples_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "examples"
