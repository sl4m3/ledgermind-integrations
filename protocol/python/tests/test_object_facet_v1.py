from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ledgermind_protocol.object_facet_v1 import (
    EmbedResult,
    GenericExecutionTask,
    IngestRawRoundRequest,
    IngestRawRoundResponse,
    OperationalExtractionInput,
    OperationalExtractionResult,
    RecordRetrievalOutcome,
    ResolutionContext,
    RetrievalRequest,
    RetrievalResponse,
)

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _ROOT / "conformance" / "object-facet-v1"
_SCHEMAS = _ROOT / "schemas" / "core-ipc" / "object-facet-v1"
_SCHEMA_NAMES = {
    "ingest-raw-round-request-v1.schema.json",
    "ingest-raw-round-response-v1.schema.json",
    "generic-execution-task-v1.schema.json",
    "resolution-context-v1.schema.json",
    "operational-extraction-input-v1.schema.json",
    "operational-extraction-result-v1.schema.json",
    "consolidation-result-v1.schema.json",
    "retrieval-request-v1.schema.json",
    "retrieval-response-v1.schema.json",
    "record-retrieval-outcome-v1.schema.json",
    "embed-result-v1.schema.json",
}

_CONTEXT_FIXTURES = {
    "v_ingest_raw_round.json": IngestRawRoundRequest,
    "v_task_generate_extract.json": GenericExecutionTask,
    "v_task_embed_texts.json": GenericExecutionTask,
    "v_extraction_single.json": OperationalExtractionResult,
    "v_extraction_multiple.json": OperationalExtractionResult,
    "v_extraction_ambiguous.json": OperationalExtractionResult,
    "v_consolidation_merge.json": None,
    "v_consolidation_replace.json": None,
    "v_retrieval_request.json": RetrievalRequest,
    "v_retrieval_soft_facets.json": RetrievalResponse,
    "v_retrieval_explanation.json": RetrievalResponse,
    "v_retrieval_structure_positive.json": RetrievalResponse,
    "v_embed_result.json": EmbedResult,
}

_CONTEXT_DEPENDENT_INVALID = {
    "i_extraction_existing_not_in_candidates.json",
    "i_extraction_ambiguous_unknown_candidate.json",
    "i_extraction_alias_not_in_source.json",
    "i_extraction_unknown_source_event.json",
}


def _canonical_bytes(model) -> bytes:
    return json.dumps(
        model.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _load_fixture(name: str, directory: str) -> dict:
    return json.loads((_FIXTURES / directory / name).read_text(encoding="utf-8"))


def _load_context() -> tuple[OperationalExtractionInput, set[str], str]:
    mentions = OperationalExtractionInput.model_validate(
        _load_fixture("mentions_v1.json", "context")
    )
    source = _load_fixture("source_v1.json", "context")
    return mentions, set(source["event_ids"]), source["text"]


def test_module_resolves_inside_this_repo() -> None:
    module = importlib.util.find_spec("ledgermind_protocol")
    assert module is not None and module.origin is not None
    assert Path(module.origin).resolve().is_relative_to(_ROOT)


def test_object_facet_schema_inventory_is_complete() -> None:
    assert {path.name for path in _SCHEMAS.glob("*.json")} == _SCHEMA_NAMES
    for path in sorted(_SCHEMAS.glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$id"].endswith(path.name)
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        if path.name != "resolution-context-v1.schema.json":
            assert schema["required"]


def test_all_valid_fixtures_validate_and_match_canonical_digests() -> None:
    digests = json.loads((_FIXTURES / "digests.json").read_text(encoding="utf-8"))
    assert digests["protocol"] == "object-facet-v1"
    for name in sorted((_FIXTURES / "valid").glob("*.json")):
        fixture_name = name.name
        model_type = _CONTEXT_FIXTURES[fixture_name]
        if model_type is None:
            continue
        payload = json.loads(name.read_text(encoding="utf-8"))
        model = model_type.model_validate(payload)
        canonical = hashlib.sha256(_canonical_bytes(model)).hexdigest()
        assert f"sha256:{canonical}" == digests["valid"][fixture_name]
        assert model_type.model_validate(json.loads(json.dumps(model.model_dump(mode="json")))) == model


def test_all_invalid_fixtures_are_rejected() -> None:
    for name in sorted((_FIXTURES / "invalid").glob("*.json")):
        fixture_name = name.name
        payload = json.loads(name.read_text(encoding="utf-8"))
        rejected = False
        try:
            model = _parse_invalid_fixture(fixture_name, payload)
            _validate_with_context(fixture_name, model)
        except (ValidationError, ValueError):
            rejected = True
        assert rejected, f"{fixture_name} was unexpectedly accepted"


def _parse_invalid_fixture(fixture_name: str, payload: dict):
    from ledgermind_protocol.object_facet_v1 import ConsolidationResult

    if fixture_name.startswith("i_extraction_"):
        return OperationalExtractionResult.model_validate(payload)
    if fixture_name == "i_ingest_scope_mismatch.json":
        return IngestRawRoundRequest.model_validate(payload)
    if fixture_name == "i_task_forbidden_trust.json":
        return GenericExecutionTask.model_validate(payload)
    if fixture_name == "i_consolidation_unknown_action.json":
        return ConsolidationResult.model_validate(payload)
    if fixture_name == "i_embed_dimension_mismatch.json":
        return EmbedResult.model_validate(payload)
    if fixture_name == "i_retrieval_missing_query_embedding.json":
        return RetrievalRequest.model_validate(payload)
    if fixture_name == "i_retrieval_structure_negative.json":
        return RetrievalResponse.model_validate(payload)
    raise AssertionError(f"no parser for {fixture_name}")


def _validate_with_context(fixture_name: str, model) -> None:
    if fixture_name.startswith("i_extraction_") and isinstance(model, OperationalExtractionResult):
        mentions, event_ids, source_text = _load_context()
        model.validate_with_source(mentions, event_ids, source_text)


def test_valid_extraction_fixtures_pass_the_shared_source_context() -> None:
    mentions, event_ids, source_text = _load_context()
    assert len(event_ids) == 3
    for fixture_name in (
        "v_extraction_single.json",
        "v_extraction_multiple.json",
        "v_extraction_ambiguous.json",
    ):
        result = OperationalExtractionResult.model_validate(_load_fixture(fixture_name, "valid"))
        result.validate_with_source(mentions, event_ids, source_text)


def test_context_dependent_invalid_fixtures_fail_only_with_source_context() -> None:
    mentions, event_ids, source_text = _load_context()
    for fixture_name in _CONTEXT_DEPENDENT_INVALID:
        result = OperationalExtractionResult.model_validate(_load_fixture(fixture_name, "invalid"))
        with pytest.raises(ValueError):
            result.validate_with_source(mentions, event_ids, source_text)


@pytest.mark.parametrize(
    "fixture_name",
    sorted(_CONTEXT_DEPENDENT_INVALID),
)
def test_context_dependent_invalid_fixture_reason(fixture_name: str) -> None:
    mentions, event_ids, source_text = _load_context()
    result = OperationalExtractionResult.model_validate(_load_fixture(fixture_name, "invalid"))
    with pytest.raises(ValueError):
        result.validate_with_source(mentions, event_ids, source_text)


def test_mention_input_context_is_valid_and_has_eight_candidates() -> None:
    mentions, _, _ = _load_context()
    by_ref = {mention.mention_ref: mention for mention in mentions.mentions}
    assert len(by_ref["m1"].candidates) == 8
    assert len(by_ref["m2"].candidates) == 4
    assert by_ref["m1"].candidates[0].object_id == "obj-postgresql"


def test_embed_result_matches_embedding_task_texts() -> None:
    task = GenericExecutionTask.model_validate(_load_fixture("v_task_embed_texts.json", "valid"))
    assert task.embedding_request is not None
    result = EmbedResult.model_validate(_load_fixture("v_embed_result.json", "valid"))
    result.validate_for_request(task.embedding_request)

    oversized = EmbedResult.model_validate(
        {
            **result.model_dump(mode="json"),
            "vectors": [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3], [0.1, 0.2, 0.3]],
        }
    )
    with pytest.raises(ValueError, match="texts count"):
        oversized.validate_for_request(task.embedding_request)

    wrong_dimensions = EmbedResult.model_validate(
        {**result.model_dump(mode="json"), "dimensions": 4, "vectors": [[0.1, 0.2, 0.3, 0.4], [0.1, 0.2, 0.3, 0.4]]}
    )
    with pytest.raises(ValueError, match="must match the requested dimensions"):
        wrong_dimensions.validate_for_request(task.embedding_request)


def test_generic_task_rejects_inconsistent_shapes() -> None:
    task = GenericExecutionTask.model_validate(_load_fixture("v_task_generate_extract.json", "valid"))
    assert task.task_kind == "generate_json"

    with pytest.raises(ValidationError, match="embedding_request"):
        GenericExecutionTask.model_validate(
            {
                **task.model_dump(mode="json", exclude_none=True),
                "embedding_request": {
                    "texts": ["text"],
                    "purpose": "object_card",
                    "dimensions": 3,
                },
            }
        )
    with pytest.raises(ValidationError, match="operation"):
        GenericExecutionTask.model_validate(
            {
                **task.model_dump(mode="json", exclude_none=True),
                "operation": "summarize",
            }
        )
    embed_task = GenericExecutionTask.model_validate(
        _load_fixture("v_task_embed_texts.json", "valid")
    )
    with pytest.raises(ValidationError, match="model_request"):
        GenericExecutionTask.model_validate(
            {
                **embed_task.model_dump(mode="json", exclude_none=True),
                "model_request": {"messages": [], "max_output_tokens": 100, "response_format": "json_object"},
            }
        )


def test_resolution_context_requires_project_with_repository() -> None:
    with pytest.raises(ValidationError, match="project id"):
        ResolutionContext.model_validate({"repository_id": "repo-1"})
    with pytest.raises(ValidationError, match="project id"):
        RetrievalRequest.model_validate(
            {
                "memory_space_id": "space-1",
                "query_text": "query",
                "query_embedding": [0.1],
                "limit": 10,
                "repository_id": "repo-1",
                "explanation_level": "compact",
            }
        )
    assert ResolutionContext.model_validate(
        {"repository_id": "repo-1", "project_id": "project-1"}
    )


def test_extraction_result_rejects_both_object_choices_and_unknown_refs() -> None:
    with pytest.raises(ValidationError):
        OperationalExtractionResult.model_validate(
            _load_fixture("i_extraction_both_object_choices.json", "invalid")
        )
    with pytest.raises(ValidationError):
        OperationalExtractionResult.model_validate(
            _load_fixture("i_extraction_unknown_object_ref.json", "invalid")
        )


def test_retrieval_response_requires_claimed_facet_activation() -> None:
    with pytest.raises(ValidationError, match="item facet"):
        RetrievalResponse.model_validate(
            _load_fixture("i_retrieval_structure_negative.json", "invalid")
        )


def test_retrieval_item_forbids_unknown_object_reasons() -> None:
    with pytest.raises(ValidationError):
        RetrievalResponse.model_validate(
            {
                "retrieval_request_id": "r1",
                "items": [
                    {
                        "value_id": "v1",
                        "primary_object_id": "obj-1",
                        "object_name": "Object",
                        "facet": "structure",
                        "content": "content",
                        "relevance": 0.9,
                        "selection_explanation": {
                            "object_reasons": ["reputation_match"],
                            "facet_activations": [
                                {"facet": "structure", "score": 0.9, "signals": []}
                            ],
                            "score_components": {
                                "semantic": 0.9,
                                "object": 0.9,
                                "facet": 0.9,
                                "scope_time": 1.0,
                                "context": 0.9,
                                "recency": 0.9,
                                "support": 0.9,
                                "usage": 0.1,
                            },
                        },
                    }
                ],
            }
        )


def test_record_retrieval_outcome_requires_delivered_within_candidates() -> None:
    outcome = RecordRetrievalOutcome(
        retrieval_request_id="r1",
        candidate_value_ids=["v1", "v2"],
        delivered_value_ids=["v1"],
        created_at="2026-08-07T12:00:00Z",
    )
    assert outcome.delivered_value_ids == ["v1"]
    with pytest.raises(ValidationError, match="not among the candidates"):
        RecordRetrievalOutcome(
            retrieval_request_id="r1",
            candidate_value_ids=["v1", "v2"],
            delivered_value_ids=["v9"],
            created_at="2026-08-07T12:00:00Z",
        )


def test_forbidden_phase_and_trust_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        OperationalExtractionResult.model_validate(
            _load_fixture("i_extraction_forbidden_phase.json", "invalid")
        )
    with pytest.raises(ValidationError):
        GenericExecutionTask.model_validate(_load_fixture("i_task_forbidden_trust.json", "invalid"))


def test_consolidation_actions_are_closed() -> None:
    payload = _load_fixture("v_consolidation_merge.json", "valid")
    with pytest.raises(ValidationError, match="keep_separate"):
        from ledgermind_protocol.object_facet_v1 import ConsolidationResult

        ConsolidationResult.model_validate({**payload, "action": "keep_separate"})


def test_ingest_response_status_is_closed() -> None:
    assert IngestRawRoundResponse(
        raw_round_id="round-1",
        duplicate=False,
        operational_job_id="job-1",
        status="queued",
    )
    with pytest.raises(ValidationError):
        IngestRawRoundResponse(
            raw_round_id="round-1",
            duplicate=False,
            operational_job_id="job-1",
            status="running",
        )


def test_canonical_repr_omits_null_optional_fields() -> None:
    result = OperationalExtractionResult.model_validate(
        _load_fixture("v_extraction_single.json", "valid")
    )
    dumped = result.model_dump(mode="json", exclude_none=True)
    assert "new_canonical_name" not in dumped["objects"][0]
    assert "scope_text" not in dumped["values"][0]
    assert "valid_from" not in dumped["values"][0]
