"""Independent checker for source-bound one-point refutation witnesses.

An accepted witness establishes one actual violation and its exact candidate
trace. It does not certify acceptance or prove that the point is the canonical
least violation.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable

from proof_dag_checker import (
    Invalid,
    Unsupported,
    OBLIGATIONS,
    ROLES,
    build_expected,
    canonical_bytes,
    digest,
    exact_equal,
    load_json_strict,
    local_value,
    validate_request,
)

SCHEMA = "finite-semantic-refutation-v1"


def _evaluate_point(circuit, names, point, tick: Callable[[str, int], None]):
    positions = {name: index for index, name in enumerate(names)}
    values = []
    for key in circuit.nodes:
        tick("refutation_cells", 1)
        op = key[0]
        if op in {"b", "u"}:
            value = key[1]
        elif op == "input":
            value = point[positions[key[1]]]
        else:
            value = local_value(op, tuple(values[child] for child in key[1:]))
        values.append(value)
    return values


def _trace(events, values):
    result = []
    for site, reachable, guard in events:
        if values[reachable]:
            result.append([site, int(bool(values[guard]))])
    return result


def check(request: dict, certificate: dict, count: Callable[[str, int], None] | None = None):
    tick = count or (lambda _kind, _n=1: None)
    domains, names, points = validate_request(request)
    if type(certificate) is not dict:
        raise Invalid("refutation certificate type")
    fields = {
        "kind", "request_id", "word_bits", "input_order", "domains",
        "source_sha256", "obligation", "input", "trace", "certificate_sha256",
    }
    if set(certificate) != fields or certificate["kind"] != SCHEMA:
        raise Invalid("refutation certificate schema")
    supplied = certificate["certificate_sha256"]
    if type(supplied) is not str or not re.fullmatch(r"[0-9a-f]{64}", supplied):
        raise Invalid("refutation digest format")
    unhashed = dict(certificate)
    del unhashed["certificate_sha256"]
    if supplied != hashlib.sha256(canonical_bytes(unhashed)).hexdigest():
        raise Invalid("refutation digest")
    if (
        not exact_equal(certificate["request_id"], request["id"])
        or not exact_equal(certificate["word_bits"], 32)
        or not exact_equal(certificate["input_order"], names)
        or not exact_equal(certificate["domains"], domains)
    ):
        raise Invalid("refutation request/domain binding")
    hashes = {role: digest(request[role]) for role in ROLES} | {
        "repair_guard": digest(request["repair_guard"])
    }
    if not exact_equal(certificate["source_sha256"], hashes):
        raise Invalid("refutation source binding")
    obligation = certificate["obligation"]
    if type(obligation) is not str or obligation not in OBLIGATIONS:
        raise Invalid("refutation obligation")
    point = certificate["input"]
    if type(point) is not list or len(point) != len(names):
        raise Invalid("refutation input")
    if any(type(value) is not int or type(value) is bool for value in point):
        raise Invalid("refutation input")
    if point not in points:
        raise Invalid("refutation input outside domain")
    trace = certificate["trace"]
    if type(trace) is not list or any(
        type(event) is not list
        or len(event) != 2
        or type(event[0]) is not int
        or type(event[0]) is bool
        or event[0] < 0
        or type(event[1]) is not int
        or type(event[1]) is bool
        or event[1] not in {0, 1}
        for event in trace
    ):
        raise Invalid("refutation trace")
    circuit, programs, _guard, roots = build_expected(request)
    values = _evaluate_point(circuit, names, point, tick)
    root = roots[OBLIGATIONS.index(obligation)]
    if values[root] is not False:
        raise Invalid("claimed obligation is true")
    expected_trace = _trace(programs["candidate"].events, values)
    if not exact_equal(trace, expected_trace):
        raise Invalid("refutation trace mismatch")
    witness = {"obligation": obligation, "trace": trace, "input": point}
    return {
        "status": "REFUTED",
        "witness": witness,
        "checked_nodes": len(circuit.nodes),
        "checked_cells": len(circuit.nodes),
        "mode": "one-point-refutation",
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("certificate", type=Path)
    args = parser.parse_args()
    try:
        request = load_json_strict(args.request.read_text())
        certificate = load_json_strict(args.certificate.read_text())
        result = check(request, certificate)
    except (Invalid, Unsupported) as exc:
        result = {"status": "INVALID", "reason": str(exc)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
