from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ledgermind_integrations.protocol import calculate_payload_digest

_ROOT = Path(__file__).resolve().parents[2]
_EXPECTED_SCHEMA_SHA256 = "f5c9af1926af03ef68eeeceb355bda0b27d1f36adfdb009b0c3bbe1557ec1fb9"
_EXPECTED_FIXTURE_DIGEST = "sha256:ba521c2887242597e69ae2cd77f0fc0b70bb8498da80bcce46ee8dc258095b61"


def test_shared_schema_and_fixture_are_canonical() -> None:
    schema = (_ROOT / "schemas" / "raw-round-v2.schema.json").read_bytes()
    fixture = json.loads(
        (_ROOT / "conformance" / "fixtures" / "hermes_complete.json").read_text(
            encoding="utf-8"
        )
    )

    assert hashlib.sha256(schema).hexdigest() == _EXPECTED_SCHEMA_SHA256
    assert calculate_payload_digest(fixture) == _EXPECTED_FIXTURE_DIGEST
