"""Minimal public ContextView models shared by clients and Local."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .models import ProtocolModel


class RetrieveContextRequest(ProtocolModel):
    api_version: Literal["1"] = "1"
    memory_space_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=20_000)
    limit: int = Field(default=5, ge=1, le=50)


class ContextViewItem(ProtocolModel):
    knowledge_id: str = Field(min_length=1, max_length=500)
    title: str
    target: str
    statement: str
    relevance: float = Field(ge=0.0, le=1.0)


class ContextView(ProtocolModel):
    api_version: Literal["1"] = "1"
    items: list[ContextViewItem]


__all__ = ["ContextView", "ContextViewItem", "RetrieveContextRequest"]
