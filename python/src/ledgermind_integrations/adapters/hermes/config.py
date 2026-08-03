"""Configuration for the standalone Hermes integration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HermesConfig:
    endpoint: str
    token_file: str
    memory_space_id: str
    source_instance_id: str
    profile_id: str
    state_db_path: str
    spool_dir: str
    adapter_version: str = "hermes-python/0.1.0"
    source_schema_version: int = 1


_REQUIRED = ("endpoint", "memory_space_id", "source_instance_id", "profile_id")


def load_config(path: str | Path) -> HermesConfig:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Hermes config must be a JSON object")
    for key in _REQUIRED:
        if not str(payload.get(key, "")).strip():
            raise ValueError(f"Hermes config requires {key}")
    return HermesConfig(
        endpoint=str(payload["endpoint"]),
        token_file=str(payload.get("token_file", "~/.ledgermind/server.token")),
        memory_space_id=str(payload["memory_space_id"]),
        source_instance_id=str(payload["source_instance_id"]),
        profile_id=str(payload["profile_id"]),
        state_db_path=str(payload.get("state_db_path", "~/.hermes/state.db")),
        spool_dir=str(payload.get("spool_dir", "~/.ledgermind/hermes-spool")),
        adapter_version=str(payload.get("adapter_version", "hermes-python/0.1.0")),
        source_schema_version=int(payload.get("source_schema_version", 1)),
    )
