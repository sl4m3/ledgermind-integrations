"""Public object-facet ContextView returned by Local."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .models import ProtocolModel
from .object_facet import MAX_CONTEXT_IDS, RetrievalItem

ContextViewItem = RetrievalItem


class ContextView(ProtocolModel):
    schema_version: Literal[2] = 2
    retrieval_request_id: str = Field(min_length=1, max_length=500)
    items: list[ContextViewItem] = Field(max_length=100)
    delivered_value_ids: list[str] = Field(default_factory=list, max_length=MAX_CONTEXT_IDS)

    @model_validator(mode="after")
    def validate_delivery_refs(self) -> ContextView:
        if len(set(self.delivered_value_ids)) != len(self.delivered_value_ids):
            raise ValueError("delivered_value_ids must be unique")
        value_ids = {item.value_id for item in self.items}
        if not set(self.delivered_value_ids).issubset(value_ids):
            raise ValueError("delivered_value_ids must refer to returned items")
        return self


__all__ = ["ContextView", "ContextViewItem"]
