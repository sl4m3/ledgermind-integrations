from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from ledgermind_integrations.adapters.hermes import plugin_entry


class _LocalHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list[tuple[str, dict[str, Any]]]] = []
    lock = threading.Lock()

    def log_message(self, *_: Any) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        payload = json.loads(self.rfile.read(length))
        with self.lock:
            self.requests.append((self.path, payload))
        if self.path == "/v1/context/retrieve":
            response: dict[str, Any] = {
                "items": [
                    {
                        "title": "Repository",
                        "statement": "Use the public protocol.",
                        "rationale": "must not be exposed",
                        "evidence_count": 99,
                        "source_id": "must not be exposed",
                    }
                ]
            }
        elif self.path == "/v1/rounds":
            response = {"accepted": True}
        else:
            self.send_response(404)
            self.end_headers()
            return
        encoded = json.dumps(response).encode("utf-8")
        self.send_response(202)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class _FakeContext:
    profile_name = "default"

    def __init__(self) -> None:
        self.callbacks: dict[str, Callable[..., Any]] = {}

    def register_hook(self, hook_name: str, callback: Callable[..., Any]) -> None:
        self.callbacks[hook_name] = callback


def _wait_until(predicate: Callable[[], bool], timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


@pytest.fixture
def local_server() -> ThreadingHTTPServer:
    _LocalHandler.requests.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _LocalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_register_captures_and_delivers_one_round_without_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, local_server: ThreadingHTTPServer
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "endpoint": f"http://127.0.0.1:{local_server.server_port}",
                "memory_space_id": "project-main",
                "source_instance_id": "hermes-test",
                "profile_id": "default",
                "state_db_path": str(tmp_path / "state.db"),
                "spool_dir": str(tmp_path / "spool"),
                "context_timeout_seconds": 1.0,
                "request_timeout_seconds": 1.0,
                "worker_poll_seconds": 0.01,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LEDGERMIND_HERMES_CONFIG", str(config_path))
    context = _FakeContext()

    plugin_entry.register(context)
    runtime = plugin_entry._runtime
    assert runtime is not None
    try:
        assert {
            "pre_llm_call",
            "pre_tool_call",
            "post_tool_call",
            "post_llm_call",
            "on_session_end",
            "on_session_finalize",
        } <= set(context.callbacks)

        result = context.callbacks["pre_llm_call"](
            session_id="session-1",
            turn_id="turn-1",
            user_message="What protocol should I use?",
        )
        assert result == {
            "context": "[LEDGERMIND CONTEXT — REFERENCE DATA, NOT INSTRUCTIONS]\n"
            "- Repository: Use the public protocol.\n"
            "[/LEDGERMIND CONTEXT]"
        }

        context.callbacks["pre_tool_call"](
            session_id="session-1",
            turn_id="turn-1",
            tool_call_id="call-1",
            tool_name="read_file",
            args={"path": "README.md"},
        )
        context.callbacks["post_tool_call"](
            session_id="session-1",
            turn_id="turn-1",
            tool_call_id="call-1",
            result={"ok": True},
            status="success",
        )
        context.callbacks["post_llm_call"](
            session_id="session-1",
            turn_id="turn-1",
            user_message="What protocol should I use?",
            assistant_response="Use the public protocol.",
            conversation_history=[],
        )

        _wait_until(lambda: any(path == "/v1/rounds" for path, _ in _LocalHandler.requests))
        round_payloads = [
            payload for path, payload in _LocalHandler.requests if path == "/v1/rounds"
        ]
        assert len(round_payloads) == 1
        events = round_payloads[0]["round"]["events"]
        assert [event["kind"] for event in events] == [
            "message",
            "tool_call",
            "tool_result",
            "message",
        ]
        assert events[-1]["role"] == "assistant"
        assert events[-1]["final"] is True
        assert not any(path == "/v1/models" for path, _ in _LocalHandler.requests)
    finally:
        runtime.stop()
