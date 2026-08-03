"""Small dependency-free validation for RawRound client boundaries."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_TOP_LEVEL = {"api_version", "idempotency_key", "memory_space_id", "source", "round", "payload_digest", "extensions"}
_SEMANTIC_FIELDS = {"hypothesis", "title", "target", "statement", "rationale", "phase", "confidence", "knowledge"}


class RawRoundValidationError(ValueError):
    """Payload is not a valid client RawRound."""


def validate_raw_round(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise RawRoundValidationError("payload must be an object")
    extra = set(payload) - _TOP_LEVEL
    if extra:
        raise RawRoundValidationError(f"unknown top-level fields: {sorted(extra)}")
    if payload.get("api_version") != "2":
        raise RawRoundValidationError("api_version must be '2'")
    for field in ("memory_space_id", "idempotency_key", "payload_digest"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise RawRoundValidationError(f"{field} must be a non-empty string")
    if not _DIGEST.fullmatch(str(payload["idempotency_key"])):
        raise RawRoundValidationError("idempotency_key must be sha256:<64 hex>")
    if not _DIGEST.fullmatch(str(payload["payload_digest"])):
        raise RawRoundValidationError("payload_digest must be sha256:<64 hex>")
    source = payload.get("source")
    round_payload = payload.get("round")
    if not isinstance(source, Mapping) or not isinstance(round_payload, Mapping):
        raise RawRoundValidationError("source and round must be objects")
    for field in ("system", "instance_id", "profile_id", "session_id", "round_id", "adapter_version"):
        if not isinstance(source.get(field), str) or not str(source[field]).strip():
            raise RawRoundValidationError(f"source.{field} must be non-empty")
    events = round_payload.get("events")
    if not isinstance(events, list) or not events:
        raise RawRoundValidationError("round.events must be a non-empty list")
    event_ids = [event.get("event_id") for event in events if isinstance(event, Mapping)]
    declared_event_ids = source.get("event_ids")
    if len(event_ids) != len(events) or len(set(event_ids)) != len(event_ids):
        raise RawRoundValidationError("round event IDs must be unique")
    if declared_event_ids != event_ids:
        raise RawRoundValidationError("source.event_ids must match round event order")
    for field in _SEMANTIC_FIELDS:
        if field in payload:
            raise RawRoundValidationError(f"semantic field is not client-owned: {field}")
    return dict(payload)
