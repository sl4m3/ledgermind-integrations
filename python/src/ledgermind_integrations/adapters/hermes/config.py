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
    allow_remote: bool = False
    context_limit: int = 5
    context_timeout_seconds: float = 1.5
    request_timeout_seconds: float = 5.0
    worker_poll_seconds: float = 0.5
    max_pending_attempts: int = 3
    max_raw_round_bytes: int = 5_000_000
    max_spool_bytes: int = 50_000_000
    max_spool_files: int = 1_000
    inflight_ttl_seconds: float = 300.0


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
        allow_remote=bool(payload.get("allow_remote", False)),
        context_limit=max(int(payload.get("context_limit", 5)), 1),
        context_timeout_seconds=max(float(payload.get("context_timeout_seconds", 1.5)), 0.1),
        request_timeout_seconds=max(float(payload.get("request_timeout_seconds", 5.0)), 0.1),
        worker_poll_seconds=max(float(payload.get("worker_poll_seconds", 0.5)), 0.05),
        max_pending_attempts=max(int(payload.get("max_pending_attempts", 3)), 1),
        max_raw_round_bytes=max(int(payload.get("max_raw_round_bytes", 5_000_000)), 1),
        max_spool_bytes=max(int(payload.get("max_spool_bytes", 50_000_000)), 1),
        max_spool_files=max(int(payload.get("max_spool_files", 1_000)), 1),
        inflight_ttl_seconds=max(float(payload.get("inflight_ttl_seconds", 300.0)), 0.1),
    )
