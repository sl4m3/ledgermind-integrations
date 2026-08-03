"""Cross-language canonical RawRound v2 serialization and digest."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, cast


def _normalize_rfc3339(value: object) -> object:
    if isinstance(value, list):
        return [_normalize_rfc3339(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_rfc3339(item) for key, item in value.items()}
    if not isinstance(value, str) or "T" not in value:
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        return value
    return parsed.isoformat().replace("+00:00", "Z")


def canonical_body(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("RawRound payload must be an object")
    round_payload = payload["round"]
    events = round_payload["events"]
    canonical_round = {
        **round_payload,
        "events": [
            {
                **event,
                "content": event.get("content", []),
                "final": event.get("final", False),
            }
            for event in events
        ],
    }
    return {
        "source": payload["source"],
        "round": canonical_round,
    }


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        _normalize_rfc3339(canonical_body(payload)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def calculate_payload_digest(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def with_payload_digest(payload: dict[str, Any]) -> dict[str, Any]:
    result = cast(dict[str, Any], json.loads(json.dumps(payload, ensure_ascii=False)))
    digest = calculate_payload_digest(result)
    result["payload_digest"] = digest
    result.setdefault("idempotency_key", digest)
    return result
