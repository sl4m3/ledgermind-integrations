"""Atomic filesystem queue for pending capture and RawRound delivery."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class SpoolStats:
    pending_capture: int
    ready_delivery: int
    failed: int


class FileSpool:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser()
        self.pending_dir = self.root / "pending-capture"
        self.ready_dir = self.root / "ready-delivery"
        self.failed_dir = self.root / "failed"

    def _ensure(self) -> None:
        for directory in (self.pending_dir, self.ready_dir, self.failed_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def _write(self, destination: Path, payload: Mapping[str, Any]) -> Path:
        self._ensure()
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
        return destination

    @staticmethod
    def _copy(payload: Mapping[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(json.dumps(dict(payload), ensure_ascii=False)))

    def enqueue_pending(self, key: str, payload: Mapping[str, Any]) -> Path:
        return self._write(self.pending_dir / f"{key}.json", self._copy(payload))

    def enqueue_ready(self, key: str, payload: Mapping[str, Any]) -> Path:
        envelope = {"request": self._copy(payload), "delivery": {"attempts": 0, "next_attempt_at": 0.0}}
        return self._write(self.ready_dir / f"{key}.json", envelope)

    def pop_pending(self, limit: int = 10) -> list[tuple[str, dict[str, Any]]]:
        self._ensure()
        result: list[tuple[str, dict[str, Any]]] = []
        for path in sorted(self.pending_dir.glob("*.json"))[: max(int(limit), 1)]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.fail_pending(path.name, "invalid_json")
                continue
            if isinstance(payload, dict):
                result.append((path.name, payload))
            else:
                self.fail_pending(path.name, "invalid_payload")
        return result

    def complete_pending(self, item_name: str) -> None:
        (self.pending_dir / item_name).unlink(missing_ok=True)

    def fail_pending(self, item_name: str, reason: str) -> Path:
        source = self.pending_dir / item_name
        target = self.failed_dir / f"pending-{item_name}"
        payload: dict[str, Any] = {"failure_reason": reason}
        if source.exists():
            try:
                raw = json.loads(source.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    payload = {**raw, "failure_reason": reason}
            except (OSError, json.JSONDecodeError):
                pass
        target_path = self._write(target, payload)
        source.unlink(missing_ok=True)
        return target_path

    def pop_ready(self, limit: int = 10) -> list[tuple[str, dict[str, Any]]]:
        self._ensure()
        result: list[tuple[str, dict[str, Any]]] = []
        for path in sorted(self.ready_dir.glob("*.json"))[: max(int(limit), 1)]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.fail(path.name, "invalid_json")
                continue
            if not isinstance(payload, dict):
                self.fail(path.name, "invalid_envelope")
                continue
            try:
                due = float(payload.get("delivery", {}).get("next_attempt_at", 0.0)) <= time.time()
            except (TypeError, ValueError, AttributeError):
                due = True
            if due:
                result.append((path.name, payload))
        return result

    def complete(self, item_name: str) -> None:
        (self.ready_dir / item_name).unlink(missing_ok=True)

    def retry(self, item_name: str, payload: Mapping[str, Any]) -> None:
        self._write(self.ready_dir / item_name, self._copy(payload))

    def fail(self, item_name: str, reason: str) -> Path:
        source = self.ready_dir / item_name
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {"delivery": {}}
        if not isinstance(payload, dict):
            payload = {"delivery": {}}
        delivery = payload.get("delivery")
        if not isinstance(delivery, dict):
            delivery = {}
        delivery["failure_reason"] = reason
        payload["delivery"] = delivery
        target = self._write(self.failed_dir / item_name, payload)
        source.unlink(missing_ok=True)
        return target

    def stats(self) -> SpoolStats:
        self._ensure()
        return SpoolStats(
            pending_capture=len(list(self.pending_dir.glob("*.json"))),
            ready_delivery=len(list(self.ready_dir.glob("*.json"))),
            failed=len(list(self.failed_dir.glob("*.json"))),
        )
