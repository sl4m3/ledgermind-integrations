"""Public Core IPC v1 envelope contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

CORE_IPC_PROTOCOL_VERSION = 1
CORE_KNOWLEDGE_SCHEMA_VERSION = 5
CORE_IPC_CAPABILITIES = frozenset(
    {
        "core_owned_backup",
        "model_task_failure_reporting",
        "projection_events",
    }
)
CORE_IPC_SUPPORTED_OPERATIONS = (
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
)
CORE_IPC_OPERATIONS = frozenset(CORE_IPC_SUPPORTED_OPERATIONS)
CORE_IPC_ERROR_CODES = (
    "INVALID_REQUEST",
    "INVALID_HYPOTHESIS",
    "IDEMPOTENCY_CONFLICT",
    "MEMORY_SPACE_MISMATCH",
    "NOT_FOUND",
    "VERSION_CONFLICT",
    "STALE_MODEL_TASK",
    "INTEGRITY_VIOLATION",
    "PROTOCOL_VERSION_UNSUPPORTED",
    "STORAGE_UNAVAILABLE",
    "INTERNAL_ERROR",
)


def _require_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


def _require_non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _require_rfc3339(value: str, name: str) -> str:
    _require_text(value, name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be RFC3339") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return value


def _require_object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return dict(value)


@dataclass(frozen=True, slots=True)
class CoreError:
    code: str
    message: str
    error_id: str
    retryable: bool

    def __post_init__(self) -> None:
        if self.code not in CORE_IPC_ERROR_CODES:
            raise ValueError(f"unknown Core IPC error code: {self.code}")
        _require_text(self.message, "error message")
        _require_text(self.error_id, "error id")
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be a boolean")

    def to_payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "error_id": self.error_id,
            "retryable": self.retryable,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CoreError:
        return cls(
            code=str(payload["code"]),
            message=str(payload["message"]),
            error_id=str(payload["error_id"]),
            retryable=payload["retryable"],
        )


@dataclass(frozen=True, slots=True)
class CoreRequestEnvelope:
    protocol_version: int
    request_id: str
    operation: str
    payload: dict[str, Any]

    _VERSION: ClassVar[int] = CORE_IPC_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.protocol_version != self._VERSION:
            raise ValueError("unsupported Core IPC protocol version")
        _require_text(self.request_id, "request id")
        if self.operation not in CORE_IPC_OPERATIONS:
            raise ValueError(f"unsupported Core IPC operation: {self.operation}")
        if not isinstance(self.payload, dict):
            raise TypeError("request payload must be an object")

    def to_payload(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "operation": self.operation,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CoreRequestEnvelope:
        return cls(
            protocol_version=int(payload["protocol_version"]),
            request_id=str(payload["request_id"]),
            operation=str(payload["operation"]),
            payload=_require_object(payload["payload"], "request payload"),
        )

    @classmethod
    def from_json(cls, payload_json: str) -> CoreRequestEnvelope:
        return cls.from_payload(_require_object(json.loads(payload_json), "request envelope"))


@dataclass(frozen=True, slots=True)
class CoreResponseEnvelope:
    protocol_version: int
    request_id: str
    status: str
    result: dict[str, Any] | None = None
    error: CoreError | None = None

    _VERSION: ClassVar[int] = CORE_IPC_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.protocol_version != self._VERSION:
            raise ValueError("unsupported Core IPC protocol version")
        _require_text(self.request_id, "request id")
        if self.status not in {"ok", "error"}:
            raise ValueError("response status must be ok or error")
        if self.status == "ok" and (self.result is None or self.error is not None):
            raise ValueError("successful response requires result and no error")
        if self.status == "error" and (self.error is None or self.result is not None):
            raise ValueError("error response requires error and no result")

    @classmethod
    def ok(cls, request_id: str, result: dict[str, Any]) -> CoreResponseEnvelope:
        return cls(
            protocol_version=CORE_IPC_PROTOCOL_VERSION,
            request_id=request_id,
            status="ok",
            result=dict(result),
        )

    @classmethod
    def from_error(cls, request_id: str, error: CoreError) -> CoreResponseEnvelope:
        return cls(
            protocol_version=CORE_IPC_PROTOCOL_VERSION,
            request_id=request_id,
            status="error",
            error=error,
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "status": self.status,
        }
        if self.status == "ok":
            payload["result"] = self.result
        else:
            payload["error"] = self.error.to_payload() if self.error is not None else None
        return payload

    def to_json(self) -> str:
        return json.dumps(
            self.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CoreResponseEnvelope:
        status = str(payload["status"])
        if status == "ok":
            return cls(
                protocol_version=int(payload["protocol_version"]),
                request_id=str(payload["request_id"]),
                status=status,
                result=_require_object(payload["result"], "response result"),
            )
        return cls(
            protocol_version=int(payload["protocol_version"]),
            request_id=str(payload["request_id"]),
            status=status,
            error=CoreError.from_payload(_require_object(payload["error"], "response error")),
        )

    @classmethod
    def from_json(cls, payload_json: str) -> CoreResponseEnvelope:
        return cls.from_payload(_require_object(json.loads(payload_json), "response envelope"))


@dataclass(frozen=True, slots=True)
class HandshakeResultPayload:
    protocol_version: int
    core_version: str
    knowledge_schema_version: int
    supported_operations: tuple[str, ...]
    capabilities: dict[str, bool]

    def __post_init__(self) -> None:
        if self.protocol_version != CORE_IPC_PROTOCOL_VERSION:
            raise ValueError("unsupported Core IPC protocol version")
        _require_text(self.core_version, "core version")
        if self.knowledge_schema_version != CORE_KNOWLEDGE_SCHEMA_VERSION:
            raise ValueError("unsupported Core knowledge schema version")
        if not self.supported_operations:
            raise ValueError("supported operations must not be empty")
        if len(set(self.supported_operations)) != len(self.supported_operations):
            raise ValueError("supported operations must be unique")
        if not set(self.supported_operations).issubset(CORE_IPC_OPERATIONS):
            raise ValueError("supported operations contain an unknown operation")
        if set(self.capabilities) != CORE_IPC_CAPABILITIES or not all(
            isinstance(value, bool) for value in self.capabilities.values()
        ):
            raise ValueError("handshake capabilities are invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "core_version": self.core_version,
            "knowledge_schema_version": self.knowledge_schema_version,
            "supported_operations": list(self.supported_operations),
            "capabilities": dict(self.capabilities),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> HandshakeResultPayload:
        operations = payload.get("supported_operations")
        capabilities = payload.get("capabilities")
        if not isinstance(operations, list) or not all(isinstance(item, str) for item in operations):
            raise TypeError("supported_operations must be an array of strings")
        if not isinstance(capabilities, dict):
            raise TypeError("capabilities must be an object")
        return cls(
            protocol_version=payload["protocol_version"],
            core_version=payload["core_version"],
            knowledge_schema_version=payload["knowledge_schema_version"],
            supported_operations=tuple(operations),
            capabilities=dict(capabilities),
        )


@dataclass(frozen=True, slots=True)
class FailModelTaskPayload:
    memory_space_id: str
    task_id: str
    worker_id: str
    error_code: str
    retryable: bool
    retry_after_seconds: int
    failed_at: str

    def __post_init__(self) -> None:
        _require_text(self.memory_space_id, "memory space id")
        _require_text(self.task_id, "task id")
        _require_text(self.worker_id, "worker id")
        _require_text(self.error_code, "error code")
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be a boolean")
        if isinstance(self.retry_after_seconds, bool) or not isinstance(self.retry_after_seconds, int):
            raise TypeError("retry_after_seconds must be an integer")
        if not 0 <= self.retry_after_seconds <= 86_400:
            raise ValueError("retry_after_seconds must be between 0 and 86400")
        _require_rfc3339(self.failed_at, "failed_at")

    def to_payload(self) -> dict[str, object]:
        return {
            "memory_space_id": self.memory_space_id,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "error_code": self.error_code,
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
            "failed_at": self.failed_at,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> FailModelTaskPayload:
        return cls(
            memory_space_id=payload["memory_space_id"],
            task_id=payload["task_id"],
            worker_id=payload["worker_id"],
            error_code=payload["error_code"],
            retryable=payload["retryable"],
            retry_after_seconds=payload["retry_after_seconds"],
            failed_at=payload["failed_at"],
        )


@dataclass(frozen=True, slots=True)
class FailModelTaskResultPayload:
    status: str
    attempts: int
    available_at: str | None
    last_error_code: str | None
    failed_at: str | None
    completed_at: str | None

    def __post_init__(self) -> None:
        if self.status not in {"pending", "failed"}:
            raise ValueError("model task failure status is invalid")
        _require_non_negative_int(self.attempts, "attempts")
        for value, name in (
            (self.available_at, "available_at"),
            (self.failed_at, "failed_at"),
            (self.completed_at, "completed_at"),
        ):
            if value is not None:
                _require_rfc3339(value, name)
        if self.last_error_code is not None:
            _require_text(self.last_error_code, "last error code")

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "attempts": self.attempts,
            "available_at": self.available_at,
            "last_error_code": self.last_error_code,
            "failed_at": self.failed_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> FailModelTaskResultPayload:
        return cls(
            status=payload["status"],
            attempts=payload["attempts"],
            available_at=payload["available_at"],
            last_error_code=payload["last_error_code"],
            failed_at=payload["failed_at"],
            completed_at=payload["completed_at"],
        )


@dataclass(frozen=True, slots=True)
class CreateBackupPayload:
    def to_payload(self) -> dict[str, object]:
        return {}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CreateBackupPayload:
        if payload:
            raise ValueError("create_backup payload must be empty")
        return cls()


@dataclass(frozen=True, slots=True)
class ValidateBackupPayload:
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        _require_text(self.relative_path, "relative path")
        _require_sha256(self.sha256)

    def to_payload(self) -> dict[str, object]:
        return {"relative_path": self.relative_path, "sha256": self.sha256}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ValidateBackupPayload:
        return cls(relative_path=payload["relative_path"], sha256=payload["sha256"])


@dataclass(frozen=True, slots=True)
class PrepareRestorePayload(ValidateBackupPayload):
    pass


@dataclass(frozen=True, slots=True)
class BackupManifestPayload:
    relative_path: str
    sha256: str
    size_bytes: int
    schema_version: int

    def __post_init__(self) -> None:
        _require_text(self.relative_path, "relative path")
        _require_sha256(self.sha256)
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative integer")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("schema_version must be an integer")
        if self.schema_version != CORE_KNOWLEDGE_SCHEMA_VERSION:
            raise ValueError("schema_version does not match the Core contract")

    def to_payload(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> BackupManifestPayload:
        return cls(
            relative_path=payload["relative_path"],
            sha256=payload["sha256"],
            size_bytes=payload["size_bytes"],
            schema_version=payload["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class PrepareRestoreResultPayload(BackupManifestPayload):
    restore_token: str
    requires_restart: bool

    def __post_init__(self) -> None:
        BackupManifestPayload.__post_init__(self)
        _require_text(self.restore_token, "restore token")
        if not isinstance(self.requires_restart, bool):
            raise TypeError("requires_restart must be a boolean")

    def to_payload(self) -> dict[str, object]:
        payload = BackupManifestPayload.to_payload(self)
        payload["restore_token"] = self.restore_token
        payload["requires_restart"] = self.requires_restart
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> PrepareRestoreResultPayload:
        return cls(
            relative_path=payload["relative_path"],
            sha256=payload["sha256"],
            size_bytes=payload["size_bytes"],
            schema_version=payload["schema_version"],
            restore_token=payload["restore_token"],
            requires_restart=payload["requires_restart"],
        )


def _require_sha256(value: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError("sha256 must be a lowercase sha256 digest")
    if any(char not in "0123456789abcdef" for char in value[7:]):
        raise ValueError("sha256 must be a lowercase sha256 digest")
    return value


__all__ = [
    "CORE_IPC_CAPABILITIES",
    "CORE_IPC_ERROR_CODES",
    "CORE_IPC_OPERATIONS",
    "CORE_IPC_PROTOCOL_VERSION",
    "CORE_IPC_SUPPORTED_OPERATIONS",
    "CORE_KNOWLEDGE_SCHEMA_VERSION",
    "BackupManifestPayload",
    "CoreError",
    "CoreRequestEnvelope",
    "CoreResponseEnvelope",
    "CreateBackupPayload",
    "FailModelTaskPayload",
    "FailModelTaskResultPayload",
    "HandshakeResultPayload",
    "PrepareRestorePayload",
    "PrepareRestoreResultPayload",
    "ValidateBackupPayload",
]
