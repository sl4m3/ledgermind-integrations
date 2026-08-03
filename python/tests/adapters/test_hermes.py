from __future__ import annotations

import json
from pathlib import Path

from ledgermind_integrations.adapters.hermes.config import HermesConfig
from ledgermind_integrations.adapters.hermes.hooks import HermesRoundCapture, PendingCaptureWorker
from ledgermind_integrations.adapters.hermes.round_capture import build_raw_round
from ledgermind_integrations.runtime.spool import FileSpool


def _config(tmp_path: Path) -> HermesConfig:
    return HermesConfig(
        endpoint="http://127.0.0.1:8765",
        token_file=str(tmp_path / "token"),
        memory_space_id="workspace_01",
        source_instance_id="src_hermes_local",
        profile_id="default",
        state_db_path=str(tmp_path / "state.db"),
        spool_dir=str(tmp_path / "spool"),
    )


def _events(final: bool = True) -> list[dict[str, object]]:
    return [
        {"event_id": "1001", "kind": "message", "role": "user", "content": "Use the repository conventions."},
        {"event_id": "1002", "kind": "tool_call", "tool_call_id": "call_1", "tool_name": "read_file", "arguments": {"path": "README.md"}},
        {"event_id": "1003", "kind": "message", "role": "assistant", "final": final, "content": "The conventions are applied."},
    ]


def test_hermes_capture_matches_reference_digest() -> None:
    payload = build_raw_round(
        memory_space_id="workspace_01",
        source_system="hermes",
        source_instance_id="src_hermes_local",
        profile_id="default",
        session_id="session_01",
        round_id="1001:1003",
        started_at="2026-08-02T20:00:00Z",
        completed_at="2026-08-02T20:01:05Z",
        events=_events(),
    )
    fixture = json.loads((Path(__file__).resolve().parents[3] / "conformance/fixtures/hermes_complete.json").read_text())
    assert payload["payload_digest"] == fixture["payload_digest"]
    assert {"title", "statement", "rationale"}.isdisjoint(payload)


def test_capture_waits_for_final_event_then_promotes(tmp_path: Path) -> None:
    capture = HermesRoundCapture(_config(tmp_path), FileSpool(tmp_path / "spool"))
    pending = capture.capture_or_defer(
        session_id="session_01", round_id="round-1", started_at="2026-08-02T20:00:00Z", completed_at="2026-08-02T20:01:05Z", events=_events(False)
    )
    assert pending.parent.name == "pending-capture"
    worker = PendingCaptureWorker(capture)
    assert worker.run_once(lambda _: _events(True)) == 1
    assert capture.spool.stats().pending_capture == 0
    assert capture.spool.stats().ready_delivery == 1
