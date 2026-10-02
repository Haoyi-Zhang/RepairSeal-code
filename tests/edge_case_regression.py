#!/usr/bin/env python3
"""Bounded regressions for producer complexity, AST safety, and selector admission.

The left-deep test runs in a subprocess with a hard timeout.  It distinguishes a
latent recursive-elaboration crash risk from the fixed behavior: controlled
rejection before elaboration.  It does not claim that the old implementation
accepted an invalid request.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import producer as producer_module
from fixture_oracle import request as fixture_request
from producer import DAG, Parser, Producer, ProducerError, Translation
from proof_dag_checker import Invalid, Unsupported, check as proof_check
from proof_dag_producer import (
    OBLIGATIONS,
    ROLES,
    SCHEMA,
    _node_record,
    _sorts,
    canonical_bytes,
    produce,
    source_digest,
)
from refutation_witness_checker import check as refutation_check
from refutation_witness_producer import produce as produce_refutation


def accepted_request(identifier: str, source: str, inputs: dict[str, list[int]], guard: str = "x == 0u") -> dict:
    return {
        "id": identifier,
        "word_bits": 32,
        "inputs": inputs,
        "original": source,
        "candidate": source,
        "reference": source,
        "repair_guard": guard,
    }


def legacy_certificate(request: dict, counts: Counter[str]) -> dict[str, Any]:
    """Recreate the pre-fix fresh-cache-per-root vector construction."""
    def tick(kind: str, amount: int = 1) -> None:
        counts[kind] += amount

    model = Producer(request, tick)
    names = list(request["inputs"])
    points = [list(point) for point in itertools.product(*(request["inputs"][name] for name in names))]
    sorts = _sorts(model.dag.nodes)
    vectors = []
    for node_id in range(len(model.dag.nodes)):
        vectors.append([
            model.dag.evaluate(node_id, dict(zip(names, point))) for point in points
        ])
    nodes = [
        _node_record(index, node, sorts[index], vectors[index])
        for index, node in enumerate(model.dag.nodes)
    ]
    role_roots = {
        role: {
            "output": model.programs[role].output,
            "defined": model.programs[role].defined,
            "trace_events": [
                {"site": site, "reachable": reachable, "guard": guard}
                for site, reachable, guard in model.programs[role].trace_events
            ],
        }
        for role in ROLES
    }
    body = {
        "kind": SCHEMA,
        "request_id": request["id"],
        "word_bits": request["word_bits"],
        "input_order": names,
        "domains": request["inputs"],
        "points": points,
        "source_sha256": {
            role: source_digest(request[role]) for role in ROLES
        } | {"repair_guard": source_digest(request["repair_guard"])},
        "nodes": nodes,
        "role_roots": role_roots,
        "guard_root": model.guard,
        "obligation_roots": dict(zip(OBLIGATIONS, model.roots)),
    }
    body["certificate_sha256"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body


def producer_complexity_regression() -> dict[str, Any]:
    terms = 48
    expr = "+".join(["x"] * terms)
    source = f"unsigned f(unsigned x) {{\nunsigned r = {expr};\nreturn r;\n}}\n"
    request = accepted_request("producer-chain-regression", source, {"x": [0, 1, 3]})
    new_counts: Counter[str] = Counter()
    new_certificate = produce(request, lambda kind, n=1: new_counts.__setitem__(kind, new_counts[kind] + n))
    old_counts: Counter[str] = Counter()
    old_certificate = legacy_certificate(request, old_counts)
    if canonical_bytes(new_certificate) != canonical_bytes(old_certificate):
        raise AssertionError("topological producer changed certificate bytes")
    nodes = len(new_certificate["nodes"])
    points = len(new_certificate["points"])
    expected = nodes * points
    if new_counts["producer_vector_cells"] != expected:
        raise AssertionError((new_counts, expected))
    if old_counts["producer_steps"] <= expected:
        raise AssertionError((old_counts, expected))
    result = proof_check(request, new_certificate)
    if result["status"] != "ACCEPT":
        raise AssertionError(result)
    return {
        "terms": terms,
        "source_characters": len(source),
        "nodes": nodes,
        "points": points,
        "topological_vector_cells": new_counts["producer_vector_cells"],
        "legacy_recursive_node_visits": old_counts["producer_steps"],
        "legacy_over_topological_ratio": old_counts["producer_steps"] / expected,
        "certificate_bytes_identical": True,
        "certificate_sha256": hashlib.sha256(canonical_bytes(new_certificate)).hexdigest(),
    }


def expression_depth(root: tuple) -> tuple[int, int]:
    stack = [(root, 1)]
    nodes = 0
    maximum = 0
    while stack:
        expr, depth = stack.pop()
        nodes += 1
        maximum = max(maximum, depth)
        if expr[0] in {"num", "var"}:
            continue
        if expr[0] in {"!", "~"}:
            stack.append((expr[1], depth + 1))
        else:
            stack.append((expr[1], depth + 1))
            stack.append((expr[2], depth + 1))
    return nodes, maximum


def left_deep_child() -> None:
    source = "unsigned f(unsigned x) {return " + "+".join(["x"] * 1500) + ";\n}\n"
    if len(source) != 3034:
        raise AssertionError(len(source))
    parser = Parser(source)
    token_count = len(parser.ts)
    if token_count != 3009:
        raise AssertionError(token_count)

    # Diagnostic bypass: recover the actual tree shape without invoking the new
    # production guard, then call the still-recursive elaborator directly.
    saved = producer_module._validate_program_tree
    producer_module._validate_program_tree = lambda _body: (0, 0)
    try:
        params, body = parser.program()
    finally:
        producer_module._validate_program_tree = saved
    return_expr = body[-1][1]
    ast_nodes, ast_depth = expression_depth(return_expr)
    if (ast_nodes, ast_depth) != (2999, 1500):
        raise AssertionError((ast_nodes, ast_depth))
    diagnostic = "completed"
    try:
        dag = DAG()
        Translation(dag, params).expression(return_expr, {"x": dag.var("x")})
    except RecursionError:
        diagnostic = "RecursionError"
    if diagnostic != "RecursionError":
        raise AssertionError(diagnostic)

    request = accepted_request("left-deep-1500", source, {"x": [0, 1]})
    producer_reason = None
    try:
        produce(request)
    except ProducerError as exc:
        producer_reason = str(exc)
    if producer_reason != "AST depth":
        raise AssertionError(("producer", producer_reason))

    base_request = fixture_request(1, "correct")
    base_request["id"] = request["id"]
    base_request["inputs"] = request["inputs"]
    for role in ("original", "candidate", "reference"):
        base_request[role] = source
    base_request["repair_guard"] = request["repair_guard"]

    # A compact package can be formed without parsing; the checker must still
    # fail closed while reconstructing the authoritative source.
    compact = produce_refutation(
        base_request, {"obligation": "defined", "trace": [], "input": [0]}
    )
    compact_reason = None
    try:
        refutation_check(base_request, compact)
    except (Invalid, Unsupported) as exc:
        compact_reason = str(exc)
    if compact_reason != "AST depth":
        raise AssertionError(("compact", compact_reason))

    # The full checker is exercised with a schema-valid certificate whose source
    # binding is updated, so rejection comes from source reconstruction.
    shallow = accepted_request(
        request["id"],
        "unsigned f(unsigned x) {\nunsigned r = x;\nreturn r;\n}\n",
        {"x": [0, 1]},
    )
    full = produce(shallow)
    full["source_sha256"] = {
        role: source_digest(base_request[role]) for role in ROLES
    } | {"repair_guard": source_digest(base_request["repair_guard"])}
    full.pop("certificate_sha256")
    full["certificate_sha256"] = hashlib.sha256(canonical_bytes(full)).hexdigest()
    full_reason = None
    try:
        proof_check(base_request, full)
    except (Invalid, Unsupported) as exc:
        full_reason = str(exc)
    if full_reason != "AST depth":
        raise AssertionError(("full", full_reason))

    long_literal_source = "unsigned f(unsigned x) {return 00000000000u;\n}\n"
    # Leading-zero rejection is secondary; literal-length rejection must occur
    # before conversion or octal handling.
    literal_request = accepted_request("literal-length", long_literal_source, {"x": [0]})
    literal_reason = None
    try:
        produce(literal_request)
    except ProducerError as exc:
        literal_reason = str(exc)
    if literal_reason != "literal length":
        raise AssertionError(("literal", literal_reason))

    print(json.dumps({
        "source_characters": len(source),
        "tokens": token_count,
        "ast_nodes": ast_nodes,
        "ast_depth": ast_depth,
        "diagnostic_guard_bypass": diagnostic,
        "production_producer_rejection": producer_reason,
        "full_checker_rejection": full_reason,
        "compact_checker_rejection": compact_reason,
        "long_literal_rejection": literal_reason,
        "wrong_acceptance_observed": False,
    }, sort_keys=True))


def isolated_left_deep_regression() -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child-left-deep"],
        text=True,
        capture_output=True,
        timeout=10,
        cwd=ROOT,
    )
    elapsed = time.monotonic() - started
    if completed.returncode:
        raise AssertionError(completed.stdout + completed.stderr)
    line = completed.stdout.strip().splitlines()[-1]
    result = json.loads(line)
    result["isolated_wall_seconds"] = elapsed
    result["timeout_seconds"] = 10
    return result


def selector_admission_regression() -> dict[str, Any]:
    source = "unsigned f(unsigned x) {\nunsigned r = x;\nreturn r;\n}\n"
    guard = "(x == 0u) || ((1u / x) > 0u)"
    request = accepted_request("selector-short-circuit-total", source, {"x": [0, 1, 2]}, guard)
    # Direct short-circuit semantics: x=0 skips division; x>0 divides safely.
    semantic_values = []
    for x in request["inputs"]["x"]:
        value = (x == 0) or ((1 // x) > 0)
        semantic_values.append(bool(value))
    if semantic_values != [True, True, False]:
        raise AssertionError(semantic_values)
    # Totality means defined at every point; truth is not required at every point.
    producer_reason = None
    try:
        produce(request)
    except ProducerError as exc:
        producer_reason = str(exc)
    if producer_reason != "guard totality not simplified to true":
        raise AssertionError(producer_reason)

    shallow = accepted_request(request["id"], source, request["inputs"], "x == 0u")
    full = produce(shallow)
    full["source_sha256"]["repair_guard"] = source_digest(guard)
    full.pop("certificate_sha256")
    full["certificate_sha256"] = hashlib.sha256(canonical_bytes(full)).hexdigest()
    checker_reason = None
    try:
        proof_check(request, full)
    except (Invalid, Unsupported) as exc:
        checker_reason = str(exc)
    if checker_reason != "guard totality not simplified to true":
        raise AssertionError(checker_reason)

    compact = produce_refutation(
        request, {"obligation": "defined", "trace": [], "input": [0]}
    )
    compact_reason = None
    try:
        refutation_check(request, compact)
    except (Invalid, Unsupported) as exc:
        compact_reason = str(exc)
    if compact_reason != "guard totality not simplified to true":
        raise AssertionError(compact_reason)

    return {
        "selector": guard,
        "domain": request["inputs"]["x"],
        "semantically_defined_at_all_domain_points": True,
        "selector_truth_values": semantic_values,
        "prototype_admitted": False,
        "producer_rejection": producer_reason,
        "full_checker_rejection": checker_reason,
        "compact_checker_rejection": compact_reason,
        "boundary": (
            "The mathematical selector semantics is short-circuit total, but the prototype "
            "admits only selectors whose reconstructed definedness simplifies directly to true."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child-left-deep", action="store_true")
    args = parser.parse_args()
    if args.child_left_deep:
        left_deep_child()
        return
    if args.output is None:
        parser.error("--output is required")
    result = {
        "schema": "edge-case-regression-v1",
        "outcome": "PASS",
        "producer_complexity": producer_complexity_regression(),
        "left_deep_ast": isolated_left_deep_regression(),
        "selector_admission": selector_admission_regression(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
