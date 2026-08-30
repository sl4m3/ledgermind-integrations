from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ledgermind_integrations.adapters.lifecycle import LifecycleConfig, handle_hook
from ledgermind_integrations.adapters.lifecycle import bridge as bridge_module


class _Client:
    def __init__(self) -> None:
        self.submitted: list[dict[str, Any]] = []

    def retrieve_context(self, **_kwargs: object) -> dict[str, Any]:
        return {
            "items": [
                {"object_name": "Rollout", "facet": "procedure", "content": "Use canary first."}
            ]
        }

    def runtime_acquire(self, **_kwargs: object) -> dict[str, str]:
        return {"lease_id": "lease-1"}

    def runtime_heartbeat(self, _lease_id: str) -> dict[str, str]:
        return {"status": "ok"}

    def runtime_release(self, _lease_id: str) -> dict[str, str]:
        return {"status": "released"}

    def submit_round(self, payload: object) -> dict[str, Any]:
        self.submitted.append(dict(payload))  # type: ignore[arg-type]
        return {"status": "accepted"}


def _config(tmp_path: Path, *, enabled: bool = True) -> LifecycleConfig:
    return LifecycleConfig(
        target="codex",
        endpoint="http://127.0.0.1:8765",
        token_file="",
        memory_space_id="codex-default",
        source_instance_id="codex-test",
        profile_id="generation-operational",
        spool_dir=str(tmp_path / "spool"),
        runtime_command="ledgermind",
        enabled=enabled,
    )


def test_recall_is_advisory_and_round_is_delivered(tmp_path: Path, monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    config = _config(tmp_path)

    response = handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-1", "prompt": "Deploy service"},
    )
    assert "REFERENCE DATA, NOT INSTRUCTIONS" in response["additional_context"]
    handle_hook(
        config,
        "PreToolUse",
        {"session_id": "session-1", "tool_name": "shell", "tool_use_id": "call-1", "tool_input": {"command": "deploy"}},
    )
    handle_hook(
        config,
        "PostToolUse",
        {"session_id": "session-1", "tool_name": "shell", "tool_use_id": "call-1", "tool_response": "ok"},
    )
    handle_hook(
        config,
        "Stop",
        {"session_id": "session-1", "last_assistant_message": "Deployment complete"},
    )

    assert len(client.submitted) == 1
    raw_round = client.submitted[0]
    assert raw_round["source"]["system"] == "codex"
    assert [event["kind"] for event in raw_round["round"]["events"]] == [
        "message",
        "tool_call",
        "tool_result",
        "message",
    ]
    state = tmp_path / "spool" / "sessions" / "session-1.json"
    assert json.loads(state.read_text(encoding="utf-8")) == {}


def test_disabled_bridge_is_a_noop(tmp_path: Path) -> None:
    assert handle_hook(
        _config(tmp_path, enabled=False),
        "UserPromptSubmit",
        {"session_id": "session-1", "prompt": "hello"},
    ) == {}
    assert not (tmp_path / "spool").exists()
