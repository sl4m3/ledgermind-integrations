from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from ledgermind_protocol.object_facet_v2 import (
    OperationalExtractionInput,
    OperationalExtractionResult,
    RawRoundContextExtension,
    RetrievalResponse,
    canonical_digest,
    validate_raw_round_extensions,
)

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _ROOT / "conformance" / "object-facet-v2"
_SCHEMAS = _ROOT / "schemas" / "core-ipc" / "object-facet-v2"

_VALID_MODELS = {
    "v_operational_input.json": OperationalExtractionInput,
    "v_extraction_existing.json": OperationalExtractionResult,
    "v_extraction_new.json": OperationalExtractionResult,
    "v_extraction_ambiguous.json": OperationalExtractionResult,
    "v_extraction_extended_name.json": OperationalExtractionResult,
    "v_context_extension.json": RawRoundContextExtension,
    "v_retrieval_direct_semantic.json": RetrievalResponse,
}
_INPUT_INVALID = {
    "i_nine_candidates.json",
    "i_candidate_duplicate_rank.json",
    "i_candidate_duplicate_object_id.json",
    "i_candidate_bad_score.json",
}
_CONTEXT_INVALID = {
    "i_context_duplicate_ids.json",
    "i_context_content.json",
    "i_context_score.json",
    "i_context_too_many_ids.json",
}
_RESULT_CONTEXT_INVALID = {
    "i_existing_scope_mismatch.json",
    "i_existing_unknown_candidate.json",
    "i_ambiguous_unknown_candidate.json",
    "i_alias_wrong_event.json",
    "i_extended_name_missing_evidence.json",
    "i_unknown_source_event.json",
}


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _load_valid(name: str) -> dict[str, Any]:
    return _load(_FIXTURES / "valid" / name)


def _load_input() -> OperationalExtractionInput:
    return OperationalExtractionInput.model_validate(_load_valid("v_operational_input.json"))


def _load_events() -> dict[str, str]:
    return cast(dict[str, str], _load(_FIXTURES / "context" / "source_events.json"))


def test_schema_inventory_is_v2_only_and_strict() -> None:
    expected = {
        "operational-extraction-input-v2.schema.json",
        "operational-extraction-result-v2.schema.json",
        "raw-round-context-v1.schema.json",
        "retrieval-response-v2.schema.json",
    }
    assert {path.name for path in _SCHEMAS.glob("*.json")} == expected
    for path in sorted(_SCHEMAS.glob("*.json")):
        schema = _load(path)
        assert schema["$id"].endswith(path.name)
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False


def test_valid_fixtures_validate_and_match_typed_digests() -> None:
    digests = _load(_FIXTURES / "digests.json")
    assert digests["protocol"] == "object-facet-v2"
    assert set(digests["valid"]) == set(_VALID_MODELS)
    for name, model_type in _VALID_MODELS.items():
        model = model_type.model_validate(_load_valid(name))
        assert canonical_digest(model) == digests["valid"][name]
        assert model_type.model_validate(
            json.loads(json.dumps(model.model_dump(mode="json")))
        ) == model


def test_operational_input_has_bounded_mentions_and_eight_ranked_candidates() -> None:
    model = _load_input()
    assert len(model.mentions) == 4
    first = model.mentions[0]
    assert len(first.candidates) == 8
    assert [candidate.rank for candidate in first.candidates] == list(range(1, 9))
    assert all(candidate.final_score <= 1 for candidate in first.candidates)

    oversized = _load_valid("v_operational_input.json")
    template = copy.deepcopy(oversized["mentions"][0])
    oversized["mentions"] = []
    for index in range(25):
        mention = copy.deepcopy(template)
        mention["mention_ref"] = f"m-{index}"
        oversized["mentions"].append(mention)
    with pytest.raises(ValidationError):
        OperationalExtractionInput.model_validate(oversized)


def test_extraction_results_bind_to_candidates_and_source_events() -> None:
    inputs = _load_input()
    events = _load_events()
    for name in (
        "v_extraction_existing.json",
        "v_extraction_new.json",
        "v_extraction_ambiguous.json",
        "v_extraction_extended_name.json",
    ):
        result = OperationalExtractionResult.model_validate(_load_valid(name))
        result.validate_with_source(inputs, events)


def test_event_specific_alias_and_extended_name_require_the_selected_event() -> None:
    inputs = _load_input()
    events = _load_events()
    valid = OperationalExtractionResult.model_validate(_load_valid("v_extraction_existing.json"))
    valid.validate_with_source(inputs, events)

    wrong_event = OperationalExtractionResult.model_validate(
        _load(_FIXTURES / "invalid" / "i_alias_wrong_event.json")
    )
    with pytest.raises(ValueError, match="selected source events"):
        wrong_event.validate_with_source(inputs, events)

    extended = OperationalExtractionResult.model_validate(
        _load_valid("v_extraction_extended_name.json")
    )
    extended.validate_with_source(inputs, events)
    missing_evidence = OperationalExtractionResult.model_validate(
        _load(_FIXTURES / "invalid" / "i_extended_name_missing_evidence.json")
    )
    with pytest.raises(ValueError, match="extended canonical name"):
        missing_evidence.validate_with_source(inputs, events)


def test_all_invalid_fixtures_are_rejected() -> None:
    invalid_dir = _FIXTURES / "invalid"
    for path in sorted(invalid_dir.glob("*.json")):
        payload = _load(path)
        if path.name in _INPUT_INVALID:
            with pytest.raises((ValidationError, ValueError)):
                OperationalExtractionInput.model_validate(payload)
        elif path.name in _CONTEXT_INVALID:
            with pytest.raises((ValidationError, ValueError)):
                validate_raw_round_extensions(payload)
        elif path.name in _RESULT_CONTEXT_INVALID:
            result = OperationalExtractionResult.model_validate(payload)
            with pytest.raises(ValueError):
                result.validate_with_source(_load_input(), _load_events())
        elif path.name in {"i_unknown_facet.json", "i_source_kind.json"}:
            with pytest.raises(ValidationError):
                OperationalExtractionResult.model_validate(payload)
        else:
            raise AssertionError(f"no parser for {path.name}")


def test_context_extension_has_ids_only_and_no_raw_round_version_change() -> None:
    context = validate_raw_round_extensions(_load_valid("v_context_extension.json"))
    assert context is not None
    assert context.ledgermind_context_v1.retrieval_request_id == "retrieval-1"
    assert context.ledgermind_context_v1.delivered_value_ids == ["value-1", "value-2"]
    assert "api_version" not in context.model_dump(mode="json")
    with pytest.raises(ValidationError):
        RawRoundContextExtension.model_validate(
            {
                "ledgermind_context_v1": {
                    "retrieval_request_id": "retrieval-1",
                    "delivered_value_ids": ["value-1"] * 101,
                }
            }
        )
    with pytest.raises(ValidationError):
        validate_raw_round_extensions({"ledgermind_context_v1": None})


def test_retrieval_explanation_keeps_item_facet_out_of_activations() -> None:
    response = RetrievalResponse.model_validate(_load_valid("v_retrieval_direct_semantic.json"))
    item = response.items[0]
    assert item.facet == "function"
    assert item.explanation.item_facet == "function"
    assert [activation.facet for activation in item.explanation.activated_facets] == ["procedure"]
    assert item.explanation.object_reasons == ["direct_value_semantic"]

    with pytest.raises(ValidationError):
        RetrievalResponse.model_validate(
            {
                **response.model_dump(mode="json"),
                "items": [
                    {
                        **response.items[0].model_dump(mode="json"),
                        "explanation": {
                            **item.explanation.model_dump(mode="json"),
                            "item_facet": "state",
                        },
                    }
                ],
            }
        )


def test_v2_result_rejects_source_kind_even_when_the_value_is_otherwise_valid() -> None:
    payload = _load_valid("v_extraction_existing.json")
    payload["values"][0]["source_kind"] = "explicit_user"
    with pytest.raises(ValidationError):
        OperationalExtractionResult.model_validate(payload)


def test_canonical_digest_is_compact_sorted_and_sha256_prefixed() -> None:
    model = _load_input()
    encoded = json.dumps(
        model.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert canonical_digest(model) == "sha256:" + hashlib.sha256(encoded).hexdigest()
