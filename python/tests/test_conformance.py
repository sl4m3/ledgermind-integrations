from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from ledgermind_protocol import (
    RawRoundValidationError,
    calculate_payload_digest,
    validate_raw_round,
)

_ROOT = Path(__file__).resolve().parents[2]
_EXPECTED_FIXTURE_DIGEST = "sha256:ba521c2887242597e69ae2cd77f0fc0b70bb8498da80bcce46ee8dc258095b61"


def test_shared_schema_and_fixture_are_canonical() -> None:
    schema = (_ROOT / "schemas" / "raw-round.schema.json").read_bytes()
    schema_object = json.loads(schema)
    assert schema_object["$id"].endswith("raw-round.schema.json")
    assert "oneOf" in schema_object["$defs"]["event"]
    fixture = json.loads(
        (_ROOT / "conformance" / "valid" / "hermes_complete.json").read_text(encoding="utf-8")
    )

    assert len(hashlib.sha256(schema).hexdigest()) == 64
    assert calculate_payload_digest(fixture) == _EXPECTED_FIXTURE_DIGEST
    assert validate_raw_round(fixture).payload_digest == _EXPECTED_FIXTURE_DIGEST


def test_all_valid_conformance_fixtures_validate() -> None:
    for path in sorted((_ROOT / "conformance" / "valid").glob("*.json")):
        validate_raw_round(json.loads(path.read_text(encoding="utf-8")))


def test_all_invalid_conformance_fixtures_are_rejected() -> None:
    for path in sorted((_ROOT / "conformance" / "invalid").glob("*.json")):
        with pytest.raises(RawRoundValidationError):
            validate_raw_round(json.loads(path.read_text(encoding="utf-8")))
