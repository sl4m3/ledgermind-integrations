"""Strict object-facet resolution and retrieval contracts."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal, TypeAlias, cast

from pydantic import Field, StrictBool, StrictInt, model_validator

from .models import ProtocolModel

MAX_MENTIONS = 24
MAX_MENTION_CANDIDATES = 8
MAX_IDENTIFIER_LENGTH = 500
MAX_ALIASES = 32
MAX_MATCH_REASONS = 16
MAX_SOURCE_EVENT_IDS = 1_000
MAX_CONTENT_LENGTH = 20_000
MAX_SCOPE_TEXT_LENGTH = 20_000
MAX_RELATED_REFS = 32
MAX_RESULT_OBJECTS = 128
MAX_RESULT_VALUES = 512
MAX_RETRIEVAL_ITEMS = 100
MAX_EXPLANATION_REASONS = 32
MAX_EXPLANATION_SIGNALS = 32
MAX_REQUESTED_FACETS = 14
MAX_CONTEXT_IDS = 100
MAX_TASK_MESSAGES = 256
MAX_OUTPUT_TOKENS = 262_144
MAX_EMBEDDING_TEXTS = 512
MAX_EMBEDDING_DIMENSIONS = 8_192
MAX_EMBEDDING_VECTORS = 512
MAX_EMBEDDING_ABSOLUTE_VALUE = 1_000_000.0
MAX_EMBEDDING_TEXT_LENGTH = 2_000
MAX_RETRIEVAL_OUTCOME_IDS = 100

Facet: TypeAlias = Literal[
    "identity",
    "property",
    "state",
    "function",
    "structure",
    "procedure",
    "maintenance",
    "risk",
    "constraint",
    "preference",
    "decision",
    "experience",
    "relation",
    "event",
]
ObjectResolution: TypeAlias = Literal["existing", "new", "ambiguous"]
ObjectReason: TypeAlias = Literal[
    "exact_alias",
    "canonical_exact",
    "lexical_similarity",
    "object_card_embedding",
    "project_match",
    "repository_match",
    "task_match",
    "related_object_match",
    "conversation_match",
    "direct_value_semantic",
]
IngestStatus: TypeAlias = Literal["queued", "processing", "completed", "failed"]
TaskKind: TypeAlias = Literal["generate_json", "embed_texts"]
ProfileSlot: TypeAlias = Literal["operational", "background", "embedding"]
EmbeddingPurpose: TypeAlias = Literal[
    "object_query",
    "object_mention",
    "object_card",
    "value_record",
    "retrieval_query",
    "facet_catalog",
]
ResponseFormat: TypeAlias = Literal["json_object", "text"]
ExplanationLevel: TypeAlias = Literal["compact", "none"]

FACET_VALUES = frozenset(
    {
        "identity",
        "property",
        "state",
        "function",
        "structure",
        "procedure",
        "maintenance",
        "risk",
        "constraint",
        "preference",
        "decision",
        "experience",
        "relation",
        "event",
    }
)
OBJECT_REASON_VALUES = frozenset(
    {
        "exact_alias",
        "canonical_exact",
        "lexical_similarity",
        "object_card_embedding",
        "project_match",
        "repository_match",
        "task_match",
        "related_object_match",
        "conversation_match",
        "direct_value_semantic",
    }
)


def _require_identifier(value: str, name: str) -> None:
    if not value or not value.strip() or len(value) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(
            f"{name} must be a non-empty string of at most {MAX_IDENTIFIER_LENGTH} characters"
        )


def _require_text(value: str, name: str, maximum: int) -> None:
    if not value or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be a non-empty string of at most {maximum} characters")


def _validate_unique(values: Sequence[object], name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _validate_ids(values: list[str], name: str, maximum: int, *, minimum: int = 1) -> None:
    if not minimum <= len(values) <= maximum:
        raise ValueError(f"{name} must contain between {minimum} and {maximum} entries")
    for value in values:
        _require_identifier(value, name.rstrip("s"))
    _validate_unique(values, name)


def _require_sha256_digest(value: str, name: str) -> None:
    if len(value) != 71 or not value.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in value[7:]
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")


def _validate_validity_window(valid_from: str | None, valid_to: str | None) -> None:
    parsed_from: datetime | None = None
    parsed_to: datetime | None = None
    if valid_from is not None:
        parsed_from = _parse_rfc3339(valid_from, "valid_from")
    if valid_to is not None:
        parsed_to = _parse_rfc3339(valid_to, "valid_to")
    if parsed_from is not None and parsed_to is not None and parsed_to < parsed_from:
        raise ValueError("valid_to must not precede valid_from")


def _parse_rfc3339(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be RFC3339") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


def _normalize_for_comparison(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(
        str.maketrans(
            cast(
                dict[str, str | int | None],
                {
                    "\u2010": "-",
                    "\u2011": "-",
                    "\u2012": "-",
                    "\u2013": "-",
                    "\u2014": "-",
                    "\u2015": "-",
                    "\u2043": "-",
                    "\u2212": "-",
                    "\ufe58": "-",
                    "\ufe63": "-",
                    "\uff0d": "-",
                    "\u2018": "'",
                    "\u2019": "'",
                    "\u201a": "'",
                    "\u201b": "'",
                    "\u201c": '"',
                    "\u201d": '"',
                    "\u201e": '"',
                    "\u201f": '"',
                },
            )
        )
    )
    normalized = " ".join(normalized.casefold().split())
    return re.sub(r"\s*-\s*", "-", normalized)


def _normalized_contains(text: str, needle: str) -> bool:
    normalized_needle = _normalize_for_comparison(needle)
    return bool(normalized_needle) and normalized_needle in _normalize_for_comparison(text)


def _component_count(value: str) -> int:
    return len(_normalize_for_comparison(value).split())


class ModelRequest(ProtocolModel):
    """Opaque generate-json request prepared by Core."""

    messages: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_TASK_MESSAGES)
    max_output_tokens: int = Field(ge=1, le=MAX_OUTPUT_TOKENS)
    response_format: ResponseFormat

    @model_validator(mode="after")
    def validate_messages(self) -> ModelRequest:
        for message in self.messages:
            if not isinstance(message, dict):
                raise TypeError("model messages must be objects")
        return self


class EmbeddingRequest(ProtocolModel):
    """Opaque embedding request prepared by Core."""

    texts: list[str] = Field(min_length=1, max_length=MAX_EMBEDDING_TEXTS)
    purpose: EmbeddingPurpose
    dimensions: int | None = Field(default=None, ge=1, le=MAX_EMBEDDING_DIMENSIONS)

    @model_validator(mode="after")
    def validate_texts(self) -> EmbeddingRequest:
        for text in self.texts:
            if not text.strip() or len(text) > MAX_EMBEDDING_TEXT_LENGTH:
                raise ValueError(
                    "embedding text must be a non-empty string of at most "
                    f"{MAX_EMBEDDING_TEXT_LENGTH} characters"
                )
        return self


class GenericExecutionTask(ProtocolModel):
    """Technical task; operation and operation_input remain Core-owned."""

    schema_version: Literal[2] = 2
    task_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    task_kind: TaskKind
    operation: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    profile_slot: ProfileSlot
    memory_space_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    expires_at: str
    lease: str | None = None
    model_request: ModelRequest | None = None
    embedding_request: EmbeddingRequest | None = None
    operation_input: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_task(self) -> GenericExecutionTask:
        _parse_rfc3339(self.expires_at, "expires_at")
        if self.lease is not None:
            _parse_rfc3339(self.lease, "lease")
        if self.task_kind == "generate_json":
            if self.profile_slot not in {"operational", "background"}:
                raise ValueError(
                    "generate_json task requires an operational or background profile slot"
                )
            if self.model_request is None:
                raise ValueError("generate_json task requires model_request")
            if self.embedding_request is not None:
                raise ValueError("generate_json task forbids embedding_request")
        else:
            if self.profile_slot != "embedding":
                raise ValueError("embed_texts task requires the embedding profile slot")
            if self.embedding_request is None:
                raise ValueError("embed_texts task requires embedding_request")
            if self.model_request is not None:
                raise ValueError("embed_texts task forbids model_request")
        if self.operation_input is not None and not isinstance(self.operation_input, dict):
            raise TypeError("operation_input must be an object")
        return self


class ResolutionContext(ProtocolModel):
    project_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    repository_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    task_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    conversation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
    )
    related_object_ids: list[str] | None = None

    @model_validator(mode="after")
    def validate_context(self) -> ResolutionContext:
        for value, name in (
            (self.project_id, "project id"),
            (self.repository_id, "repository id"),
            (self.task_id, "task id"),
            (self.conversation_id, "conversation id"),
        ):
            if value is not None:
                _require_identifier(value, name)
        if self.repository_id is not None and self.project_id is None:
            raise ValueError("repository id requires a matching project id")
        if self.related_object_ids is not None:
            _validate_ids(
                self.related_object_ids,
                "related_object_ids",
                MAX_RELATED_REFS,
                minimum=0,
            )
        return self


class IngestRawRoundRequest(ProtocolModel):
    """Core command wrapper for an already validated RawRound payload."""

    schema_version: Literal[2] = 2
    command_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    idempotency_key: str
    memory_space_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    raw_round: dict[str, Any]
    resolution_context: ResolutionContext | None = None

    @model_validator(mode="after")
    def validate_request(self) -> IngestRawRoundRequest:
        _require_sha256_digest(self.idempotency_key, "idempotency key")
        return self


class IngestRawRoundResponse(ProtocolModel):
    schema_version: Literal[2] = 2
    raw_round_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    duplicate: bool
    operational_job_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    status: IngestStatus


class ObjectCandidate(ProtocolModel):
    object_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    canonical_name: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    aliases: list[str] = Field(default_factory=list, max_length=MAX_ALIASES)
    match_reasons: list[str] = Field(default_factory=list, max_length=MAX_MATCH_REASONS)
    rank: StrictInt = Field(ge=1)
    lexical_score: float = Field(ge=0.0, le=1.0)
    embedding_score: float = Field(ge=0.0, le=1.0)
    context_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    project_match: StrictBool
    repository_match: StrictBool
    task_match: StrictBool
    related_object_match: StrictBool
    conversation_match: StrictBool
    explicit_scope_mismatch: StrictBool

    @model_validator(mode="after")
    def validate_candidate(self) -> ObjectCandidate:
        _require_identifier(self.object_id, "candidate object id")
        _require_text(self.canonical_name, "candidate canonical name", MAX_IDENTIFIER_LENGTH)
        for alias in self.aliases:
            _require_text(alias, "alias", MAX_IDENTIFIER_LENGTH)
        _validate_unique(self.aliases, "aliases")
        for reason in self.match_reasons:
            _require_text(reason, "match reason", MAX_IDENTIFIER_LENGTH)
        return self


class MentionResolutionInput(ProtocolModel):
    mention_ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    surface_text: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    normalized_text: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    source_event_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    span_start: StrictInt = Field(ge=0)
    span_end: StrictInt = Field(ge=0)
    candidate_set_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    candidates: list[ObjectCandidate] = Field(max_length=MAX_MENTION_CANDIDATES)

    @model_validator(mode="after")
    def validate_mention(self) -> MentionResolutionInput:
        _require_identifier(self.mention_ref, "mention ref")
        _require_identifier(self.source_event_id, "source event id")
        if _normalize_for_comparison(self.surface_text) != self.normalized_text:
            raise ValueError("normalized_text does not match the name normalizer")
        if self.span_end <= self.span_start:
            raise ValueError("mention span must have a positive length")
        if self.span_end > len(self.surface_text):
            raise ValueError("mention span must be within surface_text")
        object_ids = [candidate.object_id for candidate in self.candidates]
        ranks = [candidate.rank for candidate in self.candidates]
        _validate_unique(object_ids, "candidate object ids")
        _validate_unique(ranks, "candidate ranks")
        return self


class OperationalExtractionInput(ProtocolModel):
    schema_version: Literal[2] = 2
    raw_round_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    normalizer_version: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    facet_catalogue_version: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    normalized_round: dict[str, Any]
    mentions: list[MentionResolutionInput] = Field(
        min_length=1,
        max_length=MAX_MENTIONS,
    )
    resolution_context: ResolutionContext

    @model_validator(mode="after")
    def validate_input(self) -> OperationalExtractionInput:
        for value, name in (
            (self.raw_round_id, "raw round id"),
            (self.normalizer_version, "normalizer version"),
            (self.facet_catalogue_version, "facet catalogue version"),
        ):
            _require_identifier(value, name)
        mention_refs = [mention.mention_ref for mention in self.mentions]
        _validate_unique(mention_refs, "mention refs")
        return self


class ResolvedObject(ProtocolModel):
    ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    mention_ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    resolution: ObjectResolution
    existing_object_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
    )
    new_canonical_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
    )
    ambiguous_candidate_ids: list[str] = Field(
        default_factory=list,
        max_length=MAX_MENTION_CANDIDATES,
    )
    aliases_from_source: list[str] = Field(default_factory=list, max_length=MAX_ALIASES)
    source_event_ids: list[str] = Field(min_length=1, max_length=MAX_SOURCE_EVENT_IDS)
    canonical_name_source_event_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
    )

    @model_validator(mode="after")
    def validate_resolution(self) -> ResolvedObject:
        _require_identifier(self.ref, "object ref")
        _require_identifier(self.mention_ref, "mention ref")
        for alias in self.aliases_from_source:
            _require_text(alias, "source alias", MAX_IDENTIFIER_LENGTH)
        _validate_unique(self.aliases_from_source, "aliases_from_source")
        _validate_ids(self.source_event_ids, "source_event_ids", MAX_SOURCE_EVENT_IDS)
        if self.canonical_name_source_event_id is not None:
            _require_identifier(
                self.canonical_name_source_event_id,
                "canonical name source event id",
            )

        if self.resolution == "existing":
            if self.existing_object_id is None:
                raise ValueError("existing resolution requires existing_object_id")
            if self.new_canonical_name is not None or self.ambiguous_candidate_ids:
                raise ValueError("existing resolution contains new-object fields")
            if self.canonical_name_source_event_id is not None:
                raise ValueError("existing resolution forbids canonical name source evidence")
        elif self.resolution == "new":
            if self.new_canonical_name is None:
                raise ValueError("new resolution requires new_canonical_name")
            if self.existing_object_id is not None or self.ambiguous_candidate_ids:
                raise ValueError("new resolution contains existing or ambiguous fields")
        else:
            if self.new_canonical_name is None:
                raise ValueError("ambiguous resolution requires new_canonical_name")
            if self.existing_object_id is not None:
                raise ValueError("ambiguous resolution forbids existing_object_id")
            if not 2 <= len(self.ambiguous_candidate_ids) <= MAX_MENTION_CANDIDATES:
                raise ValueError("ambiguous resolution requires between 2 and 8 candidates")
            for candidate_id in self.ambiguous_candidate_ids:
                _require_identifier(candidate_id, "ambiguous candidate id")
            _validate_unique(self.ambiguous_candidate_ids, "ambiguous_candidate_ids")
        return self


class ExtractedValue(ProtocolModel):
    primary_object_ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    related_object_refs: list[str] = Field(default_factory=list, max_length=MAX_RELATED_REFS)
    facet: Facet
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    source_event_ids: list[str] = Field(min_length=1, max_length=MAX_SOURCE_EVENT_IDS)
    scope_text: str | None = Field(default=None, min_length=1, max_length=MAX_SCOPE_TEXT_LENGTH)
    valid_from: str | None = None
    valid_to: str | None = None

    @model_validator(mode="after")
    def validate_value(self) -> ExtractedValue:
        _require_identifier(self.primary_object_ref, "primary object ref")
        for object_ref in self.related_object_refs:
            _require_identifier(object_ref, "related object ref")
        _validate_unique(self.related_object_refs, "related_object_refs")
        _validate_ids(self.source_event_ids, "source_event_ids", MAX_SOURCE_EVENT_IDS)
        _validate_validity_window(self.valid_from, self.valid_to)
        return self


class OperationalExtractionResult(ProtocolModel):
    schema_version: Literal[2] = 2
    objects: list[ResolvedObject] = Field(max_length=MAX_RESULT_OBJECTS)
    values: list[ExtractedValue] = Field(max_length=MAX_RESULT_VALUES)

    @model_validator(mode="after")
    def validate_result(self) -> OperationalExtractionResult:
        object_refs = [object_.ref for object_ in self.objects]
        _validate_unique(object_refs, "object refs")
        for value in self.values:
            if value.primary_object_ref not in object_refs:
                raise ValueError(f"unknown object ref {value.primary_object_ref}")
            for object_ref in value.related_object_refs:
                if object_ref not in object_refs:
                    raise ValueError(f"unknown object ref {object_ref}")
        return self

    def validate_with_source(
        self,
        inputs: OperationalExtractionInput,
        source_events: Mapping[str, str],
    ) -> None:
        inputs.model_validate(inputs)
        known_events = set(source_events)
        for event_id, text in source_events.items():
            if not isinstance(event_id, str) or not event_id.strip() or not isinstance(text, str):
                raise ValueError("source events must map non-empty IDs to text")
        for mention in inputs.mentions:
            if mention.source_event_id not in known_events:
                raise ValueError(f"unknown source event {mention.source_event_id}")

        mentions_by_ref = {mention.mention_ref: mention for mention in inputs.mentions}
        for object_ in self.objects:
            selected_mention = mentions_by_ref.get(object_.mention_ref)
            if selected_mention is None:
                raise ValueError(f"unknown mention ref {object_.mention_ref}")
            candidates = {
                candidate.object_id: candidate for candidate in selected_mention.candidates
            }
            for event_id in object_.source_event_ids:
                if event_id not in known_events:
                    raise ValueError(f"unknown source event {event_id}")
            if selected_mention.source_event_id not in object_.source_event_ids:
                raise ValueError("object source_event_ids must include the mention source event")

            if object_.resolution == "existing":
                assert object_.existing_object_id is not None
                candidate = candidates.get(object_.existing_object_id)
                if candidate is None:
                    raise ValueError(
                        f"existing_object_id {object_.existing_object_id} is not among "
                        "the mention candidates"
                    )
                if candidate.explicit_scope_mismatch:
                    raise ValueError(
                        "existing resolution cannot select a scope-mismatched candidate"
                    )
            elif object_.resolution == "ambiguous":
                for candidate_id in object_.ambiguous_candidate_ids:
                    if candidate_id not in candidates:
                        raise ValueError(f"ambiguous candidate id {candidate_id} is unknown")

            for alias in object_.aliases_from_source:
                if not any(
                    _normalized_contains(source_events[event_id], alias)
                    for event_id in object_.source_event_ids
                ):
                    raise ValueError(f"alias {alias} is not present in the selected source events")

            if object_.canonical_name_source_event_id is not None:
                if object_.canonical_name_source_event_id not in object_.source_event_ids:
                    raise ValueError("canonical name evidence must be one of source_event_ids")
                if object_.canonical_name_source_event_id not in known_events:
                    raise ValueError(
                        f"unknown source event {object_.canonical_name_source_event_id}"
                    )

            if object_.resolution in {"new", "ambiguous"}:
                assert object_.new_canonical_name is not None
                components = _component_count(object_.new_canonical_name)
                if not 1 <= components <= 4:
                    raise ValueError("canonical name must contain between 1 and 4 components")
                if components >= 3:
                    evidence_event_id = object_.canonical_name_source_event_id
                    if evidence_event_id is None:
                        raise ValueError("extended canonical name requires source evidence")
                    if not _normalized_contains(
                        source_events[evidence_event_id],
                        object_.new_canonical_name,
                    ):
                        raise ValueError(
                            "extended canonical name is not present in its source event"
                        )
                elif not any(
                    _normalized_contains(source_events[event_id], object_.new_canonical_name)
                    for event_id in object_.source_event_ids
                ):
                    raise ValueError("new canonical name is not present in the source events")

        for value in self.values:
            for event_id in value.source_event_ids:
                if event_id not in known_events:
                    raise ValueError(f"unknown source event {event_id}")


class LedgerMindContext(ProtocolModel):
    schema_version: Literal[1] = 1
    retrieval_request_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    delivered_value_ids: list[str] = Field(max_length=MAX_CONTEXT_IDS)

    @model_validator(mode="after")
    def validate_context_extension(self) -> LedgerMindContext:
        _require_identifier(self.retrieval_request_id, "retrieval request id")
        for value_id in self.delivered_value_ids:
            _require_identifier(value_id, "delivered value id")
        _validate_unique(self.delivered_value_ids, "delivered_value_ids")
        return self


class RawRoundContextExtension(ProtocolModel):
    ledgermind_context: LedgerMindContext


def validate_raw_round_extensions(
    extensions: Mapping[str, Any] | RawRoundContextExtension,
) -> RawRoundContextExtension | None:
    """Validate ``ledgermind_context`` without changing unrelated extensions."""

    if isinstance(extensions, RawRoundContextExtension):
        return extensions
    if not isinstance(extensions, Mapping):
        raise TypeError("RawRound extensions must be an object")
    if "ledgermind_context" not in extensions:
        return None
    context = extensions["ledgermind_context"]
    return RawRoundContextExtension.model_validate({"ledgermind_context": context})


class FacetActivation(ProtocolModel):
    facet: Facet
    score: float = Field(ge=0.0, le=1.0)
    signals: list[str] = Field(default_factory=list, max_length=MAX_EXPLANATION_SIGNALS)

    @model_validator(mode="after")
    def validate_activation(self) -> FacetActivation:
        for signal in self.signals:
            _require_text(signal, "facet activation signal", MAX_IDENTIFIER_LENGTH)
        return self


class ScoreComponents(ProtocolModel):
    semantic: float = Field(ge=0.0, le=1.0)
    object: float = Field(ge=0.0, le=1.0)
    facet: float = Field(ge=0.0, le=1.0)
    scope_time: float = Field(ge=0.0, le=1.0)
    context: float = Field(ge=0.0, le=1.0)
    recency: float = Field(ge=0.0, le=1.0)
    support: float = Field(ge=0.0, le=1.0)
    usage: float = Field(ge=0.0, le=1.0)


class RetrievalExplanation(ProtocolModel):
    object_reasons: list[ObjectReason] = Field(max_length=MAX_EXPLANATION_REASONS)
    item_facet: Facet
    activated_facets: list[FacetActivation] = Field(max_length=MAX_REQUESTED_FACETS)
    score_components: ScoreComponents

    @model_validator(mode="after")
    def validate_explanation(self) -> RetrievalExplanation:
        _validate_unique(self.object_reasons, "object_reasons")
        facets = [activation.facet for activation in self.activated_facets]
        _validate_unique(facets, "activated_facets facets")
        return self


class RetrievalItem(ProtocolModel):
    value_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    primary_object_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    object_name: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    facet: Facet
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    relevance: float = Field(ge=0.0, le=1.0)
    explanation: RetrievalExplanation

    @model_validator(mode="after")
    def validate_item(self) -> RetrievalItem:
        _require_identifier(self.value_id, "value id")
        _require_identifier(self.primary_object_id, "primary object id")
        _require_text(self.object_name, "object name", MAX_IDENTIFIER_LENGTH)
        if self.explanation.item_facet != self.facet:
            raise ValueError("explanation item_facet must match the item facet")
        return self


class RetrievalRequest(ProtocolModel):
    """Core retrieval request with the query embedding supplied by Local."""

    schema_version: Literal[2] = 2
    memory_space_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    query_text: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    query_embedding: list[float] = Field(min_length=1, max_length=MAX_EMBEDDING_DIMENSIONS)
    embedding_model_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    embedding_model_version: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    limit: int = Field(ge=1, le=MAX_RETRIEVAL_ITEMS)
    project_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    repository_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    task_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    conversation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
    )
    related_object_ids: list[str] | None = None
    requested_facets: list[Facet] | None = None
    explanation_level: ExplanationLevel = "compact"

    @model_validator(mode="after")
    def validate_request(self) -> RetrievalRequest:
        if any(
            not math.isfinite(component) or abs(component) > MAX_EMBEDDING_ABSOLUTE_VALUE
            for component in self.query_embedding
        ):
            raise ValueError("query_embedding values must be finite and bounded")
        if self.repository_id is not None and self.project_id is None:
            raise ValueError("repository id requires a matching project id")
        if self.related_object_ids is not None:
            _validate_ids(self.related_object_ids, "related_object_ids", MAX_RELATED_REFS, minimum=0)
        if self.requested_facets is not None:
            if len(self.requested_facets) > MAX_REQUESTED_FACETS:
                raise ValueError(f"requested_facets must not exceed {MAX_REQUESTED_FACETS} entries")
            _validate_unique(self.requested_facets, "requested_facets")
        return self


class RetrievalResponse(ProtocolModel):
    schema_version: Literal[2] = 2
    retrieval_request_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    items: list[RetrievalItem] = Field(max_length=MAX_RETRIEVAL_ITEMS)

    @model_validator(mode="after")
    def validate_response(self) -> RetrievalResponse:
        _require_identifier(self.retrieval_request_id, "retrieval request id")
        return self


class RecordRetrievalOutcome(ProtocolModel):
    schema_version: Literal[2] = 2
    retrieval_request_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    candidate_value_ids: list[str] = Field(min_length=1, max_length=MAX_RETRIEVAL_OUTCOME_IDS)
    delivered_value_ids: list[str] = Field(max_length=MAX_RETRIEVAL_OUTCOME_IDS)
    created_at: str

    @model_validator(mode="after")
    def validate_outcome(self) -> RecordRetrievalOutcome:
        _parse_rfc3339(self.created_at, "created_at")
        _validate_ids(self.candidate_value_ids, "candidate_value_ids", MAX_RETRIEVAL_OUTCOME_IDS)
        _validate_ids(
            self.delivered_value_ids,
            "delivered_value_ids",
            MAX_RETRIEVAL_OUTCOME_IDS,
            minimum=0,
        )
        if not set(self.delivered_value_ids).issubset(set(self.candidate_value_ids)):
            raise ValueError("delivered_value_ids must be a subset of candidate_value_ids")
        return self


class EmbedResult(ProtocolModel):
    task_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    model_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    model_version: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    dimensions: int = Field(ge=1, le=MAX_EMBEDDING_DIMENSIONS)
    vectors: list[list[float]] = Field(min_length=1, max_length=MAX_EMBEDDING_VECTORS)

    @model_validator(mode="after")
    def validate_result(self) -> EmbedResult:
        for index, vector in enumerate(self.vectors):
            if len(vector) != self.dimensions:
                raise ValueError(
                    f"vector {index} dimension {len(vector)} does not match "
                    f"declared dimensions {self.dimensions}"
                )
            if any(
                not math.isfinite(component) or abs(component) > MAX_EMBEDDING_ABSOLUTE_VALUE
                for component in vector
            ):
                raise ValueError(f"vector {index} contains a non-finite or unbounded value")
        return self

    def validate_for_request(self, request: EmbeddingRequest) -> None:
        if len(self.vectors) != len(request.texts):
            raise ValueError(
                f"vectors count {len(self.vectors)} must equal texts count {len(request.texts)}"
            )
        if request.dimensions is not None and self.dimensions != request.dimensions:
            raise ValueError(
                f"dimensions {self.dimensions} must match the requested dimensions "
                f"{request.dimensions}"
            )


def _canonical_payload(payload: object) -> dict[str, Any]:
    if isinstance(payload, ProtocolModel):
        value = payload.model_dump(mode="json", exclude_none=True)
    elif isinstance(payload, Mapping):
        value = dict(payload)
    else:
        raise TypeError("object-facet payload must be an object or ProtocolModel")
    if not isinstance(value, dict):
        raise TypeError("object-facet payload must be an object")
    return value


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        _canonical_payload(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_digest(payload: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


calculate_object_facet_digest = canonical_digest

__all__ = [
    "FACET_VALUES",
    "MAX_CONTEXT_IDS",
    "MAX_EMBEDDING_DIMENSIONS",
    "MAX_EMBEDDING_TEXTS",
    "MAX_EMBEDDING_VECTORS",
    "MAX_MENTIONS",
    "MAX_MENTION_CANDIDATES",
    "MAX_OUTPUT_TOKENS",
    "MAX_TASK_MESSAGES",
    "OBJECT_REASON_VALUES",
    "EmbedResult",
    "EmbeddingPurpose",
    "EmbeddingRequest",
    "ExplanationLevel",
    "ExtractedValue",
    "Facet",
    "FacetActivation",
    "GenericExecutionTask",
    "IngestRawRoundRequest",
    "IngestRawRoundResponse",
    "IngestStatus",
    "LedgerMindContext",
    "MentionResolutionInput",
    "ModelRequest",
    "ObjectCandidate",
    "ObjectReason",
    "ObjectResolution",
    "OperationalExtractionInput",
    "OperationalExtractionResult",
    "ProfileSlot",
    "RawRoundContextExtension",
    "RecordRetrievalOutcome",
    "ResolutionContext",
    "ResolvedObject",
    "ResponseFormat",
    "RetrievalExplanation",
    "RetrievalItem",
    "RetrievalRequest",
    "RetrievalResponse",
    "ScoreComponents",
    "TaskKind",
    "calculate_object_facet_digest",
    "canonical_digest",
    "canonical_json_bytes",
    "validate_raw_round_extensions",
]
