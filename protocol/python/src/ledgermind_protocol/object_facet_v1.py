"""Object-facet memory contracts v1 (language-neutral public models)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import ProtocolModel

MAX_MENTION_CANDIDATES = 8
MAX_MENTIONS = 512
MAX_IDENTIFIER_LENGTH = 500
MAX_ALIASES = 32
MAX_MATCH_REASONS = 16
MAX_SOURCE_EVENT_IDS = 1_000
MAX_CONTENT_LENGTH = 20_000
MAX_RELATED_REFS = 32
MAX_RESULT_OBJECTS = 128
MAX_RESULT_VALUES = 512
MAX_CONSOLIDATION_SOURCES = 64
MAX_RETRIEVAL_ITEMS = 100
MAX_EXPLANATION_REASONS = 32
MAX_EXPLANATION_SIGNALS = 32
MAX_REQUESTED_FACETS = 14
MAX_EMBEDDING_TEXTS = 512
MAX_EMBEDDING_DIMENSIONS = 8_192
MAX_EMBEDDING_VECTORS = 512
MAX_EMBEDDING_ABSOLUTE_VALUE = 1_000_000.0
MAX_TASK_MESSAGES = 256
MAX_OUTPUT_TOKENS = 262_144
MAX_QUERY_TEXT_LENGTH = 20_000
MAX_SCOPE_TEXT_LENGTH = 20_000
MAX_EMBEDDING_TEXT_LENGTH = 2_000
MAX_RETRIEVAL_OUTCOME_IDS = 500

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
    }
)
SOURCE_KIND_VALUES = frozenset(
    {
        "explicit_user",
        "assistant_output",
        "tool_observation",
        "external_source",
        "derived_experience",
        "memory_echo",
    }
)
EMBEDDING_PURPOSE_VALUES = frozenset(
    {
        "object_query",
        "object_mention",
        "object_card",
        "value_record",
        "retrieval_query",
        "facet_catalog",
    }
)
GENERATE_OPERATION_VALUES = frozenset({"extract_values", "consolidate_values"})

Facet = Literal[
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
ObjectReason = Literal[
    "exact_alias",
    "canonical_exact",
    "lexical_similarity",
    "object_card_embedding",
    "project_match",
    "repository_match",
    "task_match",
    "related_object_match",
    "conversation_match",
]
IngestStatus = Literal["queued", "processing", "completed", "failed"]
TaskKind = Literal["generate_json", "embed_texts"]
ProfileSlot = Literal["operational", "background", "embedding"]
EmbeddingPurpose = Literal[
    "object_query",
    "object_mention",
    "object_card",
    "value_record",
    "retrieval_query",
    "facet_catalog",
]
ResponseFormat = Literal["json_object", "text"]
ObjectResolution = Literal["existing", "new", "ambiguous"]
SourceKind = Literal[
    "explicit_user",
    "assistant_output",
    "tool_observation",
    "external_source",
    "derived_experience",
    "memory_echo",
]
ConsolidationAction = Literal["merge", "replace"]
ExplanationLevel = Literal["compact", "none"]


def _require_rfc3339(value: str, name: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be RFC3339") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")


def _require_identifier(value: str, name: str) -> None:
    if not value or not value.strip() or len(value) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(f"{name} must be a non-empty string of at most {MAX_IDENTIFIER_LENGTH} characters")


def _require_sha256_digest(value: str, name: str) -> None:
    if len(value) != 71 or not value.startswith("sha256:") or any(
        char not in "0123456789abcdef" for char in value[7:]
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")


def _require_object(value: object, name: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")


def _validate_optional_ids(values: list[str] | None, name: str) -> None:
    if values is None:
        return
    if len(values) > MAX_RELATED_REFS:
        raise ValueError(f"{name} must not exceed {MAX_RELATED_REFS} entries")
    for value in values:
        _require_identifier(value, name.rstrip("s"))
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _validate_validity_window(
    valid_from: str | None,
    valid_to: str | None,
) -> None:
    if valid_from is not None:
        _require_rfc3339(valid_from, "valid_from")
    if valid_to is not None:
        _require_rfc3339(valid_to, "valid_to")
    if valid_from is not None and valid_to is not None:
        from_time = datetime.fromisoformat(valid_from.replace("Z", "+00:00"))
        to_time = datetime.fromisoformat(valid_to.replace("Z", "+00:00"))
        if to_time < from_time:
            raise ValueError("valid_to must not precede valid_from")


class ResolutionContext(ProtocolModel):
    project_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    repository_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    task_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    related_object_ids: list[str] | None = None

    @model_validator(mode="after")
    def validate_context(self) -> ResolutionContext:
        if self.repository_id is not None and self.project_id is None:
            raise ValueError("repository id requires a matching project id")
        _validate_optional_ids(self.related_object_ids, "related_object_ids")
        return self


class IngestRawRoundRequest(ProtocolModel):
    command_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    idempotency_key: str
    raw_round: dict[str, Any]
    resolution_context: ResolutionContext | None = None

    @model_validator(mode="after")
    def validate_request(self) -> IngestRawRoundRequest:
        _require_sha256_digest(self.idempotency_key, "idempotency key")
        return self


class IngestRawRoundResponse(ProtocolModel):
    raw_round_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    duplicate: bool
    operational_job_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    status: IngestStatus


class ModelRequest(ProtocolModel):
    messages: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_TASK_MESSAGES)
    max_output_tokens: int = Field(ge=1, le=MAX_OUTPUT_TOKENS)
    response_format: ResponseFormat

    @model_validator(mode="after")
    def validate_messages(self) -> ModelRequest:
        for message in self.messages:
            _require_object(message, "message")
        return self


class EmbeddingRequest(ProtocolModel):
    texts: list[str] = Field(min_length=1, max_length=MAX_EMBEDDING_TEXTS)
    purpose: EmbeddingPurpose
    dimensions: int | None = Field(default=None, ge=1, le=MAX_EMBEDDING_DIMENSIONS)

    @model_validator(mode="after")
    def validate_texts(self) -> EmbeddingRequest:
        for text in self.texts:
            if not text.strip() or len(text) > MAX_EMBEDDING_TEXT_LENGTH:
                raise ValueError(f"text must be a non-empty string of at most {MAX_EMBEDDING_TEXT_LENGTH} characters")
        return self


class GenericExecutionTask(ProtocolModel):
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
        _require_rfc3339(self.expires_at, "expires_at")
        if self.lease is not None:
            _require_rfc3339(self.lease, "lease")
        if self.task_kind == "generate_json":
            if self.operation not in GENERATE_OPERATION_VALUES:
                raise ValueError(
                    "generate_json task requires operation extract_values or consolidate_values"
                )
            if self.profile_slot not in {"operational", "background"}:
                raise ValueError(
                    "generate_json task requires an operational or background profile slot"
                )
            if self.model_request is None:
                raise ValueError("generate_json task requires model_request")
            if self.embedding_request is not None:
                raise ValueError("generate_json task forbids embedding_request")
        else:
            if self.operation != "embed_texts":
                raise ValueError("embed_texts task requires operation embed_texts")
            if self.profile_slot != "embedding":
                raise ValueError("embed_texts task requires the embedding profile slot")
            if self.embedding_request is None:
                raise ValueError("embed_texts task requires embedding_request")
            if self.model_request is not None:
                raise ValueError("embed_texts task forbids model_request")
        if self.operation_input is not None:
            _require_object(self.operation_input, "operation_input")
        return self


class ObjectCandidate(ProtocolModel):
    object_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    canonical_name: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    aliases: list[str] = Field(default_factory=list, max_length=MAX_ALIASES)
    match_reasons: list[str] = Field(default_factory=list, max_length=MAX_MATCH_REASONS)
    lexical_score: float = Field(ge=0.0, le=1.0)
    embedding_score: float = Field(ge=0.0, le=1.0)
    context_score: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_candidate(self) -> ObjectCandidate:
        for alias in self.aliases:
            _require_identifier(alias, "alias")
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError("aliases must be unique")
        return self


class MentionResolutionInput(ProtocolModel):
    mention_ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    surface_text: str = Field(min_length=1, max_length=MAX_QUERY_TEXT_LENGTH)
    normalized_text: str = Field(min_length=1, max_length=MAX_QUERY_TEXT_LENGTH)
    candidates: list[ObjectCandidate] = Field(max_length=MAX_MENTION_CANDIDATES)

    @model_validator(mode="after")
    def validate_mention(self) -> MentionResolutionInput:
        object_ids = [candidate.object_id for candidate in self.candidates]
        if len(set(object_ids)) != len(object_ids):
            raise ValueError("candidate object ids must be unique")
        return self


class OperationalExtractionInput(ProtocolModel):
    mentions: list[MentionResolutionInput] = Field(min_length=1, max_length=MAX_MENTIONS)

    @model_validator(mode="after")
    def validate_input(self) -> OperationalExtractionInput:
        mention_refs = [mention.mention_ref for mention in self.mentions]
        if len(set(mention_refs)) != len(mention_refs):
            raise ValueError("mention refs must be unique")
        return self


class ResolvedObject(ProtocolModel):
    ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    mention_ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    resolution: ObjectResolution
    existing_object_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    new_canonical_name: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    ambiguous_candidate_ids: list[str] = Field(default_factory=list, max_length=MAX_MENTION_CANDIDATES)
    aliases_from_source: list[str] = Field(default_factory=list, max_length=MAX_ALIASES)
    source_event_ids: list[str] = Field(min_length=1, max_length=MAX_SOURCE_EVENT_IDS)

    @model_validator(mode="after")
    def validate_resolution(self) -> ResolvedObject:
        if self.resolution == "existing":
            if self.existing_object_id is None:
                raise ValueError("existing resolution requires existing_object_id")
            if self.new_canonical_name is not None:
                raise ValueError("existing resolution forbids new_canonical_name")
            if self.ambiguous_candidate_ids:
                raise ValueError("existing resolution forbids ambiguous_candidate_ids")
        elif self.resolution == "new":
            if self.new_canonical_name is None:
                raise ValueError("new resolution requires new_canonical_name")
            if self.existing_object_id is not None:
                raise ValueError("new resolution forbids existing_object_id")
            if self.ambiguous_candidate_ids:
                raise ValueError("new resolution forbids ambiguous_candidate_ids")
        else:
            if self.new_canonical_name is None:
                raise ValueError("ambiguous resolution requires new_canonical_name")
            if self.existing_object_id is not None:
                raise ValueError("ambiguous resolution forbids existing_object_id")
            if not self.ambiguous_candidate_ids:
                raise ValueError("ambiguous resolution requires ambiguous_candidate_ids")
        for alias in self.aliases_from_source:
            _require_identifier(alias, "alias")
        if len(set(self.aliases_from_source)) != len(self.aliases_from_source):
            raise ValueError("aliases_from_source must be unique")
        for event_id in self.source_event_ids:
            _require_identifier(event_id, "source event id")
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise ValueError("source_event_ids must be unique")
        return self


class ExtractedValue(ProtocolModel):
    primary_object_ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    related_object_refs: list[str] = Field(default_factory=list, max_length=MAX_RELATED_REFS)
    facet: Facet
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    source_kind: SourceKind
    source_event_ids: list[str] = Field(min_length=1, max_length=MAX_SOURCE_EVENT_IDS)
    scope_text: str | None = Field(default=None, max_length=MAX_SCOPE_TEXT_LENGTH)
    valid_from: str | None = None
    valid_to: str | None = None

    @model_validator(mode="after")
    def validate_value(self) -> ExtractedValue:
        for object_ref in self.related_object_refs:
            _require_identifier(object_ref, "related object ref")
        if len(set(self.related_object_refs)) != len(self.related_object_refs):
            raise ValueError("related_object_refs must be unique")
        for event_id in self.source_event_ids:
            _require_identifier(event_id, "source event id")
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise ValueError("source_event_ids must be unique")
        _validate_validity_window(self.valid_from, self.valid_to)
        return self


class OperationalExtractionResult(ProtocolModel):
    objects: list[ResolvedObject] = Field(max_length=MAX_RESULT_OBJECTS)
    values: list[ExtractedValue] = Field(max_length=MAX_RESULT_VALUES)

    @model_validator(mode="after")
    def validate_result(self) -> OperationalExtractionResult:
        object_refs = [object_.ref for object_ in self.objects]
        if len(set(object_refs)) != len(object_refs):
            raise ValueError("object refs must be unique")
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
        event_ids: Sequence[str],
        source_text: str,
    ) -> None:
        known_events = set(event_ids)
        for object_ in self.objects:
            mention = next(
                (mention for mention in inputs.mentions if mention.mention_ref == object_.mention_ref),
                None,
            )
            if mention is None:
                raise ValueError(f"unknown mention ref {object_.mention_ref}")
            candidate_ids = {candidate.object_id for candidate in mention.candidates}
            if object_.resolution == "existing":
                if object_.existing_object_id is None:
                    raise ValueError("existing resolution requires existing_object_id")
                if object_.existing_object_id not in candidate_ids:
                    raise ValueError(
                        f"existing_object_id {object_.existing_object_id} is not among the mention candidates"
                    )
            elif object_.resolution == "ambiguous":
                for candidate_id in object_.ambiguous_candidate_ids:
                    if candidate_id not in candidate_ids:
                        raise ValueError(f"ambiguous candidate id {candidate_id} is unknown")
            for alias in object_.aliases_from_source:
                if alias not in source_text:
                    raise ValueError(f"alias {alias} is not present in the source events")
            for event_id in object_.source_event_ids:
                if event_id not in known_events:
                    raise ValueError(f"unknown source event {event_id}")
        for value in self.values:
            for event_id in value.source_event_ids:
                if event_id not in known_events:
                    raise ValueError(f"unknown source event {event_id}")


class ConsolidatedValue(ProtocolModel):
    primary_object_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    related_object_ids: list[str] = Field(default_factory=list, max_length=MAX_RELATED_REFS)
    facet: Facet
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    scope_text: str | None = Field(default=None, max_length=MAX_SCOPE_TEXT_LENGTH)
    valid_from: str | None = None
    valid_to: str | None = None

    @model_validator(mode="after")
    def validate_value(self) -> ConsolidatedValue:
        for object_id in self.related_object_ids:
            _require_identifier(object_id, "related object id")
        if len(set(self.related_object_ids)) != len(self.related_object_ids):
            raise ValueError("related_object_ids must be unique")
        _validate_validity_window(self.valid_from, self.valid_to)
        return self


class ConsolidationResult(ProtocolModel):
    action: ConsolidationAction
    source_value_ids: list[str] = Field(min_length=1, max_length=MAX_CONSOLIDATION_SOURCES)
    result: ConsolidatedValue

    @model_validator(mode="after")
    def validate_result(self) -> ConsolidationResult:
        for value_id in self.source_value_ids:
            _require_identifier(value_id, "source value id")
        if len(set(self.source_value_ids)) != len(self.source_value_ids):
            raise ValueError("source_value_ids must be unique")
        return self


class RetrievalRequest(ProtocolModel):
    memory_space_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    query_text: str = Field(min_length=1, max_length=MAX_QUERY_TEXT_LENGTH)
    query_embedding: list[float] = Field(min_length=1, max_length=MAX_EMBEDDING_DIMENSIONS)
    limit: int = Field(ge=1, le=100)
    project_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    repository_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    task_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    related_object_ids: list[str] | None = None
    requested_facets: list[Facet] | None = None
    explanation_level: ExplanationLevel

    @model_validator(mode="after")
    def validate_request(self) -> RetrievalRequest:
        for component in self.query_embedding:
            if not isinstance(component, float) or not abs(component) <= MAX_EMBEDDING_ABSOLUTE_VALUE:
                raise ValueError("query_embedding values must be finite and bounded")
        if self.repository_id is not None and self.project_id is None:
            raise ValueError("repository id requires a matching project id")
        _validate_optional_ids(self.related_object_ids, "related_object_ids")
        if self.requested_facets is not None:
            if len(self.requested_facets) > MAX_REQUESTED_FACETS:
                raise ValueError(f"requested_facets must not exceed {MAX_REQUESTED_FACETS} entries")
            if len(set(self.requested_facets)) != len(self.requested_facets):
                raise ValueError("requested_facets must be unique")
        return self


class FacetActivation(ProtocolModel):
    facet: Facet
    score: float = Field(ge=0.0, le=1.0)
    signals: list[str] = Field(default_factory=list, max_length=MAX_EXPLANATION_SIGNALS)


class ScoreComponents(ProtocolModel):
    semantic: float = Field(ge=0.0, le=1.0)
    object: float = Field(ge=0.0, le=1.0)
    facet: float = Field(ge=0.0, le=1.0)
    scope_time: float = Field(ge=0.0, le=1.0)
    context: float = Field(ge=0.0, le=1.0)
    recency: float = Field(ge=0.0, le=1.0)
    support: float = Field(ge=0.0, le=1.0)
    usage: float = Field(ge=0.0, le=1.0)


class SelectionExplanation(ProtocolModel):
    object_reasons: list[ObjectReason] = Field(min_length=1, max_length=MAX_EXPLANATION_REASONS)
    facet_activations: list[FacetActivation] = Field(min_length=1, max_length=MAX_REQUESTED_FACETS)
    score_components: ScoreComponents

    @model_validator(mode="after")
    def validate_explanation(self) -> SelectionExplanation:
        if len(set(self.object_reasons)) != len(self.object_reasons):
            raise ValueError("object_reasons must be unique")
        facets = [activation.facet for activation in self.facet_activations]
        if len(set(facets)) != len(facets):
            raise ValueError("facet_activations facets must be unique")
        return self


class RetrievalItem(ProtocolModel):
    value_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    primary_object_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    object_name: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    facet: Facet
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    relevance: float = Field(ge=0.0, le=1.0)
    selection_explanation: SelectionExplanation

    @model_validator(mode="after")
    def validate_item(self) -> RetrievalItem:
        claimed = next(
            (activation for activation in self.selection_explanation.facet_activations if activation.facet == self.facet),
            None,
        )
        if claimed is None:
            raise ValueError("facet_activations must contain the item facet")
        for activation in self.selection_explanation.facet_activations:
            if activation.score > claimed.score:
                raise ValueError("the item facet must carry the maximum facet activation")
        return self


class RetrievalResponse(ProtocolModel):
    retrieval_request_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    items: list[RetrievalItem] = Field(max_length=MAX_RETRIEVAL_ITEMS)


class RecordRetrievalOutcome(ProtocolModel):
    retrieval_request_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    candidate_value_ids: list[str] = Field(min_length=1, max_length=MAX_RETRIEVAL_OUTCOME_IDS)
    delivered_value_ids: list[str] = Field(default_factory=list, max_length=MAX_RETRIEVAL_OUTCOME_IDS)
    created_at: str

    @model_validator(mode="after")
    def validate_outcome(self) -> RecordRetrievalOutcome:
        _require_rfc3339(self.created_at, "created_at")
        for value_id in self.candidate_value_ids:
            _require_identifier(value_id, "candidate value id")
        if len(set(self.candidate_value_ids)) != len(self.candidate_value_ids):
            raise ValueError("candidate_value_ids must be unique")
        for value_id in self.delivered_value_ids:
            _require_identifier(value_id, "delivered value id")
        if len(set(self.delivered_value_ids)) != len(self.delivered_value_ids):
            raise ValueError("delivered_value_ids must be unique")
        for delivered in self.delivered_value_ids:
            if delivered not in self.candidate_value_ids:
                raise ValueError(f"delivered value id {delivered} is not among the candidates")
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
                    f"vector {index} dimension {len(vector)} does not match declared dimensions {self.dimensions}"
                )
            for component in vector:
                if not isinstance(component, float) or not abs(component) <= MAX_EMBEDDING_ABSOLUTE_VALUE:
                    raise ValueError(f"vector {index} contains a non-finite or unbounded value")
        return self

    def validate_for_request(self, request: EmbeddingRequest) -> None:
        if len(self.vectors) != len(request.texts):
            raise ValueError(
                f"vectors count {len(self.vectors)} must equal texts count {len(request.texts)}"
            )
        if request.dimensions is not None and self.dimensions != request.dimensions:
            raise ValueError(
                f"dimensions {self.dimensions} must match the requested dimensions {request.dimensions}"
            )


__all__ = [
    "FACET_VALUES",
    "GENERATE_OPERATION_VALUES",
    "MAX_EMBEDDING_DIMENSIONS",
    "MAX_EMBEDDING_TEXTS",
    "MAX_EMBEDDING_VECTORS",
    "MAX_MENTION_CANDIDATES",
    "OBJECT_REASON_VALUES",
    "SOURCE_KIND_VALUES",
    "ConsolidatedValue",
    "ConsolidationResult",
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
    "MentionResolutionInput",
    "ModelRequest",
    "ObjectCandidate",
    "ObjectReason",
    "ObjectResolution",
    "OperationalExtractionInput",
    "OperationalExtractionResult",
    "ProfileSlot",
    "RecordRetrievalOutcome",
    "ResolutionContext",
    "ResolvedObject",
    "ResponseFormat",
    "RetrievalItem",
    "RetrievalRequest",
    "RetrievalResponse",
    "ScoreComponents",
    "SelectionExplanation",
    "SourceKind",
    "TaskKind",
]
