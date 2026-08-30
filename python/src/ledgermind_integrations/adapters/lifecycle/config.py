"""Configuration shared by non-Hermes lifecycle adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LifecycleConfig:
    target: str
    endpoint: str
    token_file: str
    memory_space_id: str
    source_instance_id: str
    profile_id: str
    spool_dir: str
    runtime_command: str
    enabled: bool = True
    context_limit: int = 5
    request_timeout_seconds: float = 5.0
    heartbeat_seconds: float = 10.0
    adapter_version: str = "lifecycle-python/0.1.0"
    allow_remote: bool = False


_REQUIRED = (
    "target",
    "endpoint",
    "memory_space_id",
    "source_instance_id",
    "profile_id",
    "spool_dir",
    "runtime_command",
)


def load_lifecycle_config(path: str | Path) -> LifecycleConfig:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("integration config must be a JSON object")
    for key in _REQUIRED:
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError(f"integration config requires {key}")
    return LifecycleConfig(
        target=str(payload["target"]),
        endpoint=str(payload["endpoint"]).rstrip("/"),
        token_file=str(payload.get("token_file", "")),
        memory_space_id=str(payload["memory_space_id"]),
        source_instance_id=str(payload["source_instance_id"]),
        profile_id=str(payload["profile_id"]),
        spool_dir=str(payload["spool_dir"]),
        runtime_command=str(payload["runtime_command"]),
        enabled=bool(payload.get("enabled", True)),
        context_limit=max(int(payload.get("context_limit", 5)), 1),
        request_timeout_seconds=max(
            float(payload.get("request_timeout_seconds", 5.0)), 0.1
        ),
        heartbeat_seconds=max(float(payload.get("heartbeat_seconds", 10.0)), 0.1),
        adapter_version=str(
            payload.get("adapter_version", "lifecycle-python/0.1.0")
        ),
        allow_remote=bool(payload.get("allow_remote", False)),
    )


__all__ = ["LifecycleConfig", "load_lifecycle_config"]
