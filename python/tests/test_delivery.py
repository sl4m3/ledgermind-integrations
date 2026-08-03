from __future__ import annotations

from pathlib import Path

from ledgermind_integrations.runtime.delivery import DeliveryWorker
from ledgermind_integrations.runtime.spool import FileSpool


class FakeClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def submit_round(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        return {"status": "accepted"}


def test_delivery_sends_only_request_and_completes(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")
    payload = {"api_version": "2", "memory_space_id": "workspace", "source": {}, "round": {}, "payload_digest": "sha256:" + "a" * 64, "idempotency_key": "sha256:" + "a" * 64}
    spool.enqueue_ready(payload["idempotency_key"], payload)
    client = FakeClient()
    worker = DeliveryWorker(spool, client)

    assert worker.run_once() is True
    assert client.payloads == [payload]
    assert spool.stats().ready_delivery == 0
