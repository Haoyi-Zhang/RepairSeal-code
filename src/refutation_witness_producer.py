"""Untrusted packager for compact finite refutation witnesses."""
from __future__ import annotations

import hashlib
from typing import Any

from proof_dag_producer import canonical_bytes, source_digest

SCHEMA = "finite-semantic-refutation-v1"
ROLES = ("original", "candidate", "reference")


def produce(request: dict, witness: dict) -> dict[str, Any]:
    """Bind one claimed violation and trace to the exact receiver request."""
    body: dict[str, Any] = {
        "kind": SCHEMA,
        "request_id": request["id"],
        "word_bits": request["word_bits"],
        "input_order": list(request["inputs"]),
        "domains": request["inputs"],
        "source_sha256": {role: source_digest(request[role]) for role in ROLES}
        | {"repair_guard": source_digest(request["repair_guard"])},
        "obligation": witness["obligation"],
        "input": witness["input"],
        "trace": witness["trace"],
    }
    body["certificate_sha256"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body
