"""Read-only, schema-tolerant observation of Hermes state.db messages."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class HermesStateReader:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    def session_events(self, session_id: str) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        connection = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=1.0)
        connection.row_factory = sqlite3.Row
        try:
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(messages)")}
            selected = [
                name
                for name in (
                    "id",
                    "role",
                    "content",
                    "api_content",
                    "tool_call_id",
                    "tool_name",
                    "tool_calls",
                )
                if name in columns
            ]
            if not {"id", "role"}.issubset(columns):
                return []
            rows = connection.execute(
                f"SELECT {', '.join(selected)} FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            events: list[dict[str, Any]] = []
            for row in rows:
                content = (
                    row["api_content"]
                    if "api_content" in columns and row["api_content"]
                    else row["content"]
                )
                event: dict[str, Any] = {
                    "event_id": str(row["id"]),
                    "kind": "message",
                    "role": str(row["role"]),
                    "content": content or "",
                }
                if "tool_call_id" in columns and row["tool_call_id"]:
                    event["tool_call_id"] = str(row["tool_call_id"])
                if "tool_name" in columns and row["tool_name"]:
                    event["tool_name"] = str(row["tool_name"])
                if "tool_calls" in columns and row["tool_calls"]:
                    try:
                        event["arguments"] = json.loads(row["tool_calls"])
                    except (TypeError, json.JSONDecodeError):
                        event["arguments"] = row["tool_calls"]
                events.append(event)
            if events and events[-1].get("role") == "assistant":
                events[-1]["final"] = True
            return events
        finally:
            connection.close()
