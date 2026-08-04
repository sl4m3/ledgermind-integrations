"""Public Core IPC v1 envelope contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, ClassVar

CORE_IPC_PROTOCOL_VERSION = 1
CORE_IPC_OPERATIONS = frozenset(
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
        "shutdown",
    }
)
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


__all__ = [
    "CORE_IPC_ERROR_CODES",
    "CORE_IPC_OPERATIONS",
    "CORE_IPC_PROTOCOL_VERSION",
    "CoreError",
    "CoreRequestEnvelope",
    "CoreResponseEnvelope",
]
