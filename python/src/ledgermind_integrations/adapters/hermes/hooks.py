"""Hermes capture hooks and delayed final-event promotion."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ...runtime.spool import FileSpool
from .config import HermesConfig
from .round_capture import build_raw_round


class HermesRoundCapture:
    def __init__(self, config: HermesConfig, spool: FileSpool | None = None) -> None:
        self.config = config
        self.spool = spool or FileSpool(config.spool_dir)

    def capture_or_defer(
        self,
        *,
        session_id: str,
        round_id: str,
        started_at: str,
        completed_at: str,
        events: Sequence[Mapping[str, Any]],
    ) -> Path:
        if not events or not any(bool(event.get("final")) for event in events):
            pending = {
                "session_id": session_id,
                "round_id": round_id,
                "started_at": started_at,
                "completed_at": completed_at,
                "events": [dict(event) for event in events],
            }
            return self.spool.enqueue_pending(round_id, pending)
        payload = build_raw_round(
            memory_space_id=self.config.memory_space_id,
            source_system="hermes",
            source_instance_id=self.config.source_instance_id,
            profile_id=self.config.profile_id,
            session_id=session_id,
            round_id=round_id,
            started_at=started_at,
            completed_at=completed_at,
            events=events,
            adapter_version=self.config.adapter_version,
            source_schema_version=self.config.source_schema_version,
        )
        return self.spool.enqueue_ready(payload["idempotency_key"], payload)


class PendingCaptureWorker:
    """Promote pending captures after state.db exposes a final event."""

    def __init__(self, capture: HermesRoundCapture) -> None:
        self.capture = capture

    def run_once(self, resolver: Callable[[Mapping[str, Any]], Sequence[Mapping[str, Any]] | None]) -> int:
        promoted = 0
        for item_name, pending in self.capture.spool.pop_pending():
            events = resolver(pending)
            if not events or not any(bool(event.get("final")) for event in events):
                continue
            payload = build_raw_round(
                memory_space_id=self.capture.config.memory_space_id,
                source_system="hermes",
                source_instance_id=self.capture.config.source_instance_id,
                profile_id=self.capture.config.profile_id,
                session_id=str(pending["session_id"]),
                round_id=str(pending["round_id"]),
                started_at=str(pending["started_at"]),
                completed_at=str(pending["completed_at"]),
                events=events,
                adapter_version=self.capture.config.adapter_version,
                source_schema_version=self.capture.config.source_schema_version,
            )
            self.capture.spool.enqueue_ready(payload["idempotency_key"], payload)
            self.capture.spool.complete_pending(item_name)
            promoted += 1
        return promoted
