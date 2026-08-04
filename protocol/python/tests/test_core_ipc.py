from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledgermind_protocol.core_ipc import (
    CORE_IPC_ERROR_CODES,
    CORE_IPC_OPERATIONS,
    BackupManifestPayload,
    CoreError,
    CoreRequestEnvelope,
    CoreResponseEnvelope,
    CreateBackupPayload,
    FailModelTaskPayload,
    HandshakeResultPayload,
    PrepareRestorePayload,
    PrepareRestoreResultPayload,
    ValidateBackupPayload,
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
    "fail-model-task-v1.schema.json",
    "create-backup-v1.schema.json",
    "validate-backup-v1.schema.json",
    "prepare-restore-v1.schema.json",
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
    for operation in ("poll_model_tasks", "submit_model_result", "fail_model_task"):
        envelope = CoreRequestEnvelope(1, "request-1", operation, {})
        assert envelope.to_payload()["operation"] == operation


def test_complete_core_operation_inventory_is_advertisable() -> None:
    assert CORE_IPC_OPERATIONS == frozenset(
        {
            "handshake",
            "health",
            "accept_hypothesis",
            "retrieve_context",
            "record_context_usage",
            "poll_projection_events",
            "ack_projection_events",
            "poll_model_tasks",
            "submit_model_result",
            "fail_model_task",
            "create_backup",
            "validate_backup",
            "prepare_restore",
            "shutdown",
        }
    )
    handshake = HandshakeResultPayload(
        protocol_version=1,
        core_version="0.1.0",
        knowledge_schema_version=5,
        supported_operations=tuple(sorted(CORE_IPC_OPERATIONS)),
        capabilities={
            "core_owned_backup": True,
            "model_task_failure_reporting": True,
            "projection_events": True,
        },
    )
    payload = handshake.to_payload()
    assert payload["knowledge_schema_version"] == 5
    capabilities = payload["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["core_owned_backup"] is True


def test_failure_and_backup_payloads_round_trip() -> None:
    failure = FailModelTaskPayload(
        memory_space_id="space-1",
        task_id="task-1",
        worker_id="worker-1",
        error_code="provider_timeout",
        retryable=True,
        retry_after_seconds=30,
        failed_at="2026-08-04T12:00:00Z",
    )
    assert FailModelTaskPayload.from_payload(failure.to_payload()) == failure

    validate = ValidateBackupPayload(
        relative_path="exchange/incoming/snapshot.sqlite",
        sha256="sha256:" + "a" * 64,
    )
    prepare = PrepareRestorePayload.from_payload(validate.to_payload())
    assert prepare.relative_path == validate.relative_path
    assert prepare.sha256 == validate.sha256

    manifest = BackupManifestPayload(
        relative_path="exchange/outgoing/snapshot.sqlite",
        sha256="sha256:" + "b" * 64,
        size_bytes=42,
        schema_version=5,
    )
    prepared = PrepareRestoreResultPayload(
        restore_token="token-1",
        relative_path="exchange/incoming/snapshot.sqlite",
        sha256=validate.sha256,
        size_bytes=42,
        schema_version=5,
        requires_restart=True,
    )
    assert BackupManifestPayload.from_payload(manifest.to_payload()) == manifest
    assert prepared.to_payload()["requires_restart"] is True
    assert CreateBackupPayload.from_payload({}).to_payload() == {}
