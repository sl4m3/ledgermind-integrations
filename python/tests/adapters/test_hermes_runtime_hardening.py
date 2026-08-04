from __future__ import annotations

import json
import stat
import time
from pathlib import Path
from typing import Any, cast

import pytest

from ledgermind_integrations.adapters.hermes.config import HermesConfig
from ledgermind_integrations.adapters.hermes.hooks import HermesRoundCapture, PendingCaptureWorker
from ledgermind_integrations.adapters.hermes.runtime import HermesPluginRuntime
from ledgermind_integrations.runtime.spool import FileSpool, SpoolFullError


def _config(tmp_path: Path) -> HermesConfig:
    return HermesConfig(
        endpoint="http://127.0.0.1:8765",
        token_file=str(tmp_path / "token"),
        memory_space_id="workspace_01",
        source_instance_id="src_hermes_local",
        profile_id="default",
        state_db_path=str(tmp_path / "state.db"),
        spool_dir=str(tmp_path / "spool"),
        context_timeout_seconds=0.1,
        max_pending_attempts=2,
    )


def _pending(tmp_path: Path) -> tuple[HermesRoundCapture, FileSpool]:
    spool = FileSpool(tmp_path / "spool")
    capture = HermesRoundCapture(_config(tmp_path), spool)
    capture.capture_or_defer(
        session_id="session-1",
        round_id="round-1",
        started_at="2026-08-02T20:00:00Z",
        completed_at="2026-08-02T20:01:00Z",
        events=[],
    )
    return capture, spool


def test_spool_is_private_and_claims_ready_atomically(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", inflight_ttl_seconds=0.1)
    ready = spool.enqueue_ready("round-1", {"id": "round-1"})
    assert stat.S_IMODE(spool.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(spool.ready_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(ready.stat().st_mode) == 0o600

    claimed = spool.pop_ready()
    assert [name for name, _ in claimed] == ["round-1.json"]
    assert not ready.exists()
    assert (spool.inflight_dir / "round-1.json").exists()
    assert claimed[0][1]["delivery"]["worker_id"]
    assert claimed[0][1]["delivery"]["claimed_at"]


def test_spool_reclaims_expired_inflight(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", inflight_ttl_seconds=0.1)
    spool.enqueue_ready("round-1", {"id": "round-1"})
    spool.pop_ready()
    inflight = spool.inflight_dir / "round-1.json"
    old = time.time() - 10
    payload = json.loads(inflight.read_text(encoding="utf-8"))
    payload["delivery"]["claimed_at"] = old
    inflight.write_text(json.dumps(payload), encoding="utf-8")

    spool._reclaim_expired_inflight()
    assert not inflight.exists()
    assert (spool.ready_dir / "round-1.json").exists()
    assert [name for name, _ in spool.pop_ready()] == ["round-1.json"]


def test_spool_rejects_queue_over_limits(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", max_files=1)
    spool.enqueue_ready("round-1", {"id": "round-1"})
    with pytest.raises(SpoolFullError):
        spool.enqueue_ready("round-2", {"id": "round-2"})


def test_spool_rejects_raw_round_over_shared_payload_limit(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", max_payload_bytes=10)

    with pytest.raises(SpoolFullError, match="payload byte limit exceeded"):
        spool.enqueue_ready("round-1", {"payload": "too-large"})


def test_spool_keys_cannot_escape_queue_directory(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")

    path = spool.enqueue_pending("../../escape", {"id": "round-1"})

    assert path.parent == spool.pending_dir
    assert path.resolve().is_relative_to(spool.pending_dir.resolve())
    assert not (tmp_path / "escape.json").exists()


def test_spool_moves_do_not_count_source_twice(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", max_files=1, inflight_ttl_seconds=0.1)
    spool.enqueue_ready("round-1", {"id": "round-1"})
    item_name, payload = spool.pop_ready()[0]
    spool.retry(item_name, payload)
    assert (spool.ready_dir / item_name).exists()


def test_spool_backoff_move_does_not_count_inflight_source_twice(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", max_files=1)
    spool.enqueue_ready("round-1", {"id": "round-1"})
    item_name, payload = spool.pop_ready()[0]
    payload["delivery"]["next_attempt_at"] = time.time() + 60
    spool.retry(item_name, payload)

    assert spool.pop_ready() == []
    assert (spool.ready_dir / item_name).exists()


def test_pending_capture_is_failed_after_max_attempts(tmp_path: Path) -> None:
    capture, spool = _pending(tmp_path)
    worker = PendingCaptureWorker(capture, max_attempts=2)

    assert worker.run_once(lambda _: None) == 0
    pending = spool.pop_pending()
    assert len(pending) == 1
    assert pending[0][1]["delivery"]["attempts"] == 1
    assert worker.run_once(lambda _: None) == 0
    assert spool.stats().pending_capture == 0
    assert spool.stats().failed == 1


def test_pending_promotion_survives_ready_queue_full(tmp_path: Path) -> None:
    capture, spool = _pending(tmp_path)

    def reject_enqueue(*_args: Any, **_kwargs: Any) -> Path:
        raise SpoolFullError("test queue full")

    spool.enqueue_ready = reject_enqueue  # type: ignore[method-assign]
    worker = PendingCaptureWorker(capture, max_attempts=2)
    final_events = [
        {
            "event_id": "round-1:user",
            "kind": "message",
            "role": "user",
            "content": "hello",
        },
        {
            "event_id": "round-1:assistant",
            "kind": "message",
            "role": "assistant",
            "content": "world",
            "final": True,
        },
    ]

    assert worker.run_once(lambda _: final_events) == 0
    assert spool.stats().pending_capture == 1


def test_pending_promotion_reuses_its_queue_slot(tmp_path: Path) -> None:
    capture, spool = _pending(tmp_path)
    spool.max_files = 1
    worker = PendingCaptureWorker(capture, max_attempts=2)
    final_events = [
        {
            "event_id": "round-1:user",
            "kind": "message",
            "role": "user",
            "content": "hello",
        },
        {
            "event_id": "round-1:assistant",
            "kind": "message",
            "role": "assistant",
            "content": "world",
            "final": True,
        },
    ]

    assert worker.run_once(lambda _: final_events) == 1
    assert spool.stats().pending_capture == 0
    assert spool.stats().ready_delivery == 1


def test_post_llm_does_not_raise_when_capture_and_pending_spool_are_full(
    tmp_path: Path,
) -> None:
    spool = FileSpool(tmp_path / "spool", max_files=1)
    spool.enqueue_ready("occupied", {"id": "occupied"})
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(Any, object()),
        spool=spool,
    )
    try:
        runtime.on_post_llm_call(
            session_id="session-1",
            turn_id="turn-1",
            user_message="hello",
            assistant_response="world",
        )
    finally:
        runtime.stop()


def test_pre_llm_context_timeout_is_bounded(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(
            Any,
            type(
                "SlowClient",
                (),
                {"retrieve_context": lambda *_args, **_kwargs: time.sleep(1.0)},
            )(),
        ),
        spool=FileSpool(tmp_path / "spool"),
    )
    started = time.monotonic()
    try:
        assert runtime.on_pre_llm_call(user_message="slow") is None
    finally:
        runtime.stop()
    assert time.monotonic() - started < 0.5


def test_pre_llm_malformed_context_fails_open(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(
            Any,
            type("MalformedClient", (), {"retrieve_context": lambda *_args, **_kwargs: None})(),
        ),
        spool=FileSpool(tmp_path / "spool"),
    )
    try:
        assert runtime.on_pre_llm_call(user_message="hello") is None
    finally:
        runtime.stop()


def test_post_llm_wakes_delivery_loop(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(Any, object()),
        spool=FileSpool(tmp_path / "spool"),
    )
    woken: list[bool] = []
    runtime.loop.wake = lambda: woken.append(True)  # type: ignore[attr-defined]
    try:
        runtime.on_post_llm_call(
            session_id="session-1",
            turn_id="turn-1",
            user_message="hello",
            assistant_response="world",
        )
    finally:
        runtime.stop()
    assert woken == [True]
