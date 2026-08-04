from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledgermind_protocol.core_ipc import (
    CORE_IPC_ERROR_CODES,
    CoreError,
    CoreRequestEnvelope,
    CoreResponseEnvelope,
)

_SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schemas" / "core-ipc"
_SCHEMA_NAMES = {
    "handshake-v1.schema.json",
    "request-envelope-v1.schema.json",
    "response-envelope-v1.schema.json",
    "accept-hypothesis-v1.schema.json",
    "retrieve-context-v1.schema.json",
    "context-view-v1.schema.json",
    "record-context-usage-v1.schema.json",
    "model-task-v1.schema.json",
    "model-result-v1.schema.json",
    "projection-event-v1.schema.json",
    "error-v1.schema.json",
}


def test_core_ipc_schema_inventory_is_complete() -> None:
    assert {path.name for path in _SCHEMA_ROOT.glob("*.json")} == _SCHEMA_NAMES


def test_request_envelope_round_trips_canonical_json() -> None:
    envelope = CoreRequestEnvelope(
        protocol_version=1,
        request_id="request-1",
        operation="health",
        payload={"verbose": False},
    )

    encoded = envelope.to_json()

    assert encoded == (
        '{"operation":"health","payload":{"verbose":false},'
        '"protocol_version":1,"request_id":"request-1"}'
    )
    assert CoreRequestEnvelope.from_json(encoded) == envelope


def test_response_error_has_closed_code_and_retryability() -> None:
    response = CoreResponseEnvelope.from_error(
        request_id="request-1",
        error=CoreError(
            code="STORAGE_UNAVAILABLE",
            message="storage unavailable",
            error_id="error-1",
            retryable=True,
        ),
    )

    decoded = json.loads(response.to_json())

    assert decoded["status"] == "error"
    assert decoded["error"]["retryable"] is True
    assert set(CORE_IPC_ERROR_CODES) >= {"STORAGE_UNAVAILABLE", "INTERNAL_ERROR"}
    assert CoreResponseEnvelope.from_json(response.to_json()) == response


def test_envelopes_reject_unsupported_versions_and_unknown_operations() -> None:
    with pytest.raises(ValueError, match="protocol version"):
        CoreRequestEnvelope(2, "request-1", "health", {}).to_json()

    with pytest.raises(ValueError, match="operation"):
        CoreRequestEnvelope(1, "request-1", "not-an-operation", {}).to_json()


def test_projection_operations_are_part_of_core_ipc_v1() -> None:
    for operation in ("poll_projection_events", "ack_projection_events"):
        envelope = CoreRequestEnvelope(1, "request-1", operation, {})
        assert envelope.to_payload()["operation"] == operation

    with pytest.raises(ValueError, match="error code"):
        CoreError("NOT_A_CORE_ERROR", "bad", "error-1", False)


def test_model_task_operations_are_part_of_core_ipc_v1() -> None:
    for operation in ("poll_model_tasks", "submit_model_result"):
        envelope = CoreRequestEnvelope(1, "request-1", operation, {})
        assert envelope.to_payload()["operation"] == operation
