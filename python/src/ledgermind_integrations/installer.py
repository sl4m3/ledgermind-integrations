"""Installation entry point for client adapters."""

from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path


def install_hermes(destination: str | Path | None = None) -> Path:
    root = Path(destination or "~/.hermes/plugins").expanduser() / "ledgermind-hermes"
    root.mkdir(parents=True, exist_ok=True)
    source = files("ledgermind_integrations.adapters.hermes").joinpath("plugin.yaml")
    target = root / "plugin.yaml"
    with source.open("rb") as source_handle, target.open("wb") as target_handle:
        shutil.copyfileobj(source_handle, target_handle)
    return target
