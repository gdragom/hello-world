"""Prompt version registry — treat prompts like code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt_bundle(version: str | None = None) -> dict[str, Any]:
    path = PROMPTS_DIR / "versions.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    active = version or data["active_version"]
    for bundle in data["versions"]:
        if bundle["version"] == active:
            return bundle
    raise KeyError(f"Unknown prompt version: {active}")


def list_prompt_versions() -> list[str]:
    data = yaml.safe_load((PROMPTS_DIR / "versions.yaml").read_text(encoding="utf-8"))
    return [v["version"] for v in data["versions"]]
