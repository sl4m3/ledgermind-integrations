from __future__ import annotations

import json
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from ledgermind_integrations.runtime.delivery import DeliveryWorker, RoundSubmitter
from ledgermind_integrations.runtime.spool import FileSpool


class FakeClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def submit_round(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        return {"status": "accepted"}


def test_delivery_sends_only_request_and_completes(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")
    payload = {
        "schema_version": 2,
        "memory_space_id": "workspace",
        "source": {},
        "round": {},
        "payload_digest": "sha256:" + "a" * 64,
        "idempotency_key": "sha256:" + "a" * 64,
    }
    spool.enqueue_ready(payload["idempotency_key"], payload)
    client = FakeClient()
    worker = DeliveryWorker(spool, client)

    assert worker.run_once() is True
    assert client.payloads == [payload]
    assert spool.stats().ready_delivery == 0


def test_delivery_failure_metadata_does_not_include_exception_payload(tmp_path: Path) -> None:
    class FailingClient:
        def submit_round(self, _payload: Mapping[str, Any]) -> dict[str, Any]:
            raise RuntimeError("payload=TOP_SECRET")

    spool = FileSpool(tmp_path / "spool")
    payload = {
        "schema_version": 2,
        "memory_space_id": "workspace",
        "source": {},
        "round": {},
        "payload_digest": "sha256:" + "b" * 64,
        "idempotency_key": "sha256:" + "b" * 64,
    }
    spool.enqueue_ready(payload["idempotency_key"], payload)

    DeliveryWorker(spool, cast(RoundSubmitter, FailingClient())).run_once()

    failed = next(spool.failed_dir.glob("*.json"))
    failed_text = failed.read_text(encoding="utf-8")
    assert "TOP_SECRET" not in failed_text
    assert json.loads(failed_text)["delivery"]["failure_reason"] == "delivery_error"


def test_spool_delivery_status_is_content_free_and_clearable(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")

    spool.note_delivery_failure("RuntimeError: payload=TOP_SECRET")

    payload = json.loads(spool.delivery_status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pending"
    assert payload["reason"] == "RuntimeError"
    assert "TOP_SECRET" not in spool.delivery_status_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(spool.delivery_status_path.stat().st_mode) == 0o600
    spool.clear_delivery_failure()
    assert not spool.delivery_status_path.exists()
