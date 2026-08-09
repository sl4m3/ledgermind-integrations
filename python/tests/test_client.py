from __future__ import annotations

from typing import Any

import pytest

import ledgermind_integrations
from ledgermind_integrations.runtime.client import (
    LedgerMindClient,
    LedgerMindResponseError,
)


def _client() -> LedgerMindClient:
    return LedgerMindClient(endpoint="http://127.0.0.1:8765")


def _response() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "retrieval_request_id": "retrieval-1",
        "delivered_value_ids": ["value-1"],
        "items": [
            {
                "value_id": "value-1",
                "primary_object_id": "object-1",
                "object_name": "Repository",
                "facet": "property",
                "content": "Use the public protocol.",
                "relevance": 0.9,
                "explanation": {
                    "object_reasons": ["direct_value_semantic"],
                    "item_facet": "property",
                    "activated_facets": [],
                    "score_components": {
                        "semantic": 0.9,
                        "object": 0.0,
                        "facet": 0.0,
                        "scope_time": 0.0,
                        "context": 0.0,
                        "recency": 0.0,
                        "support": 0.0,
                        "usage": 0.0,
                    },
                },
            }
        ],
    }


def test_integration_package_exports_client_boundary() -> None:
    assert "LedgerMindClient" in ledgermind_integrations.__all__
    assert ledgermind_integrations.LedgerMindClient is LedgerMindClient


def test_client_returns_strict_context_view(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    requests: list[dict[str, Any]] = []

    def request(_method: str, _path: str, payload: dict[str, Any]) -> dict[str, Any]:
        requests.append(payload)
        return _response()

    monkeypatch.setattr(client, "_request", request)

    response = client.retrieve_context(memory_space_id="space-1", query="protocol")

    assert response["retrieval_request_id"] == "retrieval-1"
    assert response["items"][0]["value_id"] == "value-1"
    assert requests == [{"memory_space_id": "space-1", "query": "protocol", "limit": 5}]


def test_client_uses_stable_http_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    paths: list[str] = []

    def request(_method: str, path: str, _payload: dict[str, Any] | None) -> dict[str, Any]:
        paths.append(path)
        return {}

    monkeypatch.setattr(client, "_request", request)

    client.ping()
    client.health_live()
    client.health_capture_ready()
    client.health_full_ready()
    client.health()
    client.health_details()

    assert paths == [
        "/ping",
        "/health/live",
        "/health/capture-ready",
        "/health/full-ready",
        "/health/ready",
        "/health/details",
    ]


def test_client_rejects_legacy_context_item_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    legacy = {"items": [{"knowledge_id": "k1", "title": "old", "statement": "old"}]}
    monkeypatch.setattr(client, "_request", lambda *_args, **_kwargs: legacy)

    with pytest.raises(LedgerMindResponseError, match="ContextView"):
        client.retrieve_context(memory_space_id="space-1", query="protocol")
