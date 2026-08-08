"""Structural Hermes event -> RawRound conversion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ledgermind_protocol import validate_raw_round, with_payload_digest
from ledgermind_protocol.object_facet_v2 import validate_raw_round_extensions


def _content(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        return [{"type": "text", "text": value}]
    if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
        return [dict(item) for item in value]
    return [{"type": "json", "data": value}]


def normalize_event(event: Mapping[str, Any], sequence: int, round_id: str) -> dict[str, Any]:
    event_id = str(event.get("event_id") or event.get("id") or f"{round_id}:{sequence}")
    kind = str(event.get("kind") or "message")
    if kind not in {"message", "tool_call", "tool_result"}:
        kind = "message"
    result: dict[str, Any] = {
        "event_id": event_id,
        "sequence": sequence,
        "kind": kind,
        "content": _content(event.get("content", event.get("api_content"))),
        "final": bool(event.get("final", False)),
    }
    for key in ("role", "tool_call_id", "tool_name", "arguments", "status"):
        if key in event and event[key] is not None:
            result[key] = event[key]
    if kind == "tool_call" and "arguments" not in result:
        result["arguments"] = {}
    if kind == "tool_result" and "status" not in result:
        result["status"] = "unknown"
    return result


def build_raw_round(
    *,
    memory_space_id: str,
    source_system: str,
    source_instance_id: str,
    profile_id: str,
    session_id: str,
    round_id: str,
    started_at: str,
    completed_at: str,
    events: Sequence[Mapping[str, Any]],
    adapter_version: str = "hermes-python/0.1.0",
    source_schema_version: int = 1,
    extensions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = [normalize_event(event, index, round_id) for index, event in enumerate(events)]
    event_ids = [event["event_id"] for event in normalized]
    payload = {
        "api_version": "2",
        "idempotency_key": "sha256:" + "0" * 64,
        "memory_space_id": memory_space_id,
        "source": {
            "system": source_system,
            "instance_id": source_instance_id,
            "profile_id": profile_id,
            "session_id": session_id,
            "round_id": round_id,
            "first_event_id": event_ids[0],
            "final_event_id": event_ids[-1],
            "event_ids": event_ids,
            "source_schema_version": source_schema_version,
            "adapter_version": adapter_version,
        },
        "round": {
            "started_at": started_at,
            "completed_at": completed_at,
            "events": normalized,
        },
    }
    if extensions is not None:
        payload["extensions"] = dict(extensions)
    result = with_payload_digest(payload)
    result["idempotency_key"] = result["payload_digest"]
    if extensions is not None:
        validate_raw_round_extensions(result["extensions"])
    validate_raw_round(result)
    return result
