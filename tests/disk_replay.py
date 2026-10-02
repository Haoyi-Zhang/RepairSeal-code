#!/usr/bin/env python3
"""Reload every retained authoritative request and replay its retained result.

This gate is intentionally different from the generative reproducibility check.
It first parses requests from disk, verifies their ordered input maps against the
real deterministic generators/seeds (never against a certificate), and only
then invokes the receiver.  It covers 80 fixture requests, 300 structured
stress requests, and 400 post-hoc grammar requests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import resource
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from fixture_oracle import request as fixture_request
from holdout_differential import case as grammar_case, oracle as grammar_oracle
from proof_dag_checker import (
    Invalid,
    Unsupported,
    canonical_bytes,
    check as proof_check,
    evaluate_topological,
    exact_equal,
    load_json_strict,
)
from proof_dag_producer import produce
from refutation_witness_checker import check as refutation_check
from refutation_witness_producer import produce as produce_refutation
from structured_study import stress_request

FIXTURE_RE = re.compile(r"fixture-(\d{2})-(correct|overfit|regression|undefined)")
STRESS_RE = re.compile(r"stress-(\d{3})-(correct|overfit|regression|undefined)")


def strict_load(path: Path) -> Any:
    try:
        return load_json_strict(path.read_text(encoding="utf-8"))
    except (Invalid, Unsupported) as exc:
        raise AssertionError(f"strict JSON load failed for {path}: {exc}") from exc


def assert_authoritative_request(actual: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    """Compare a retained request with its generator while preserving coordinates."""
    if type(actual) is not dict or type(expected) is not dict:
        raise AssertionError(f"{label}: request type")
    if list(actual.get("inputs", {})) != list(expected.get("inputs", {})):
        raise AssertionError(
            f"{label}: authoritative input order mismatch: "
            f"disk={list(actual.get('inputs', {}))!r}, generator={list(expected.get('inputs', {}))!r}"
        )
    if not exact_equal(actual, expected):
        raise AssertionError(f"{label}: request content differs from deterministic generator")


def rows_by_id(path: Path) -> dict[str, dict[str, Any]]:
    rows = strict_load(path)
    if type(rows) is not list or any(type(row) is not dict for row in rows):
        raise AssertionError(f"{path}: expected list of objects")
    result = {row["id"]: row for row in rows}
    if len(result) != len(rows):
        raise AssertionError(f"{path}: duplicate ids")
    return result


def check_core_request(
    request_path: Path,
    certificate_path: Path,
    expected_request: dict[str, Any],
    retained_row: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = strict_load(request_path)
    certificate = strict_load(certificate_path)
    assert_authoritative_request(request, expected_request, request_path.name)
    result = proof_check(request, certificate)
    direct = evaluate_topological(request)
    for observed in (result, direct):
        if observed["status"] != retained_row["status"] or not exact_equal(observed["witness"], retained_row["witness"]):
            raise AssertionError((request["id"], retained_row, observed))
    if result["checked_nodes"] != retained_row["nodes"]:
        raise AssertionError((request["id"], "nodes", result["checked_nodes"], retained_row["nodes"]))
    if result["checked_cells"] != retained_row["nodes"] * retained_row["points"]:
        raise AssertionError((request["id"], "cells"))
    if len(canonical_bytes(certificate)) != retained_row["certificate_bytes"]:
        raise AssertionError((request["id"], "certificate bytes"))
    return request, result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof-data", type=Path, default=ROOT / "proof-data")
    parser.add_argument("--grammar-data", type=Path,
                        help="grammar result directory; defaults to <proof-data>/holdout-differential")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = args.proof_data.resolve()
    grammar_data = (args.grammar_data.resolve() if args.grammar_data
                    else data / "holdout-differential")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    fixture_rows = rows_by_id(data / "fixture-cases.json")
    stress_rows = rows_by_id(data / "stress-cases.json")
    grammar_rows = rows_by_id(grammar_data / "cases.json")
    refutation_rows = rows_by_id(data / "refutation-witnesses.json")

    requests: dict[str, dict[str, Any]] = {}
    core_results: dict[str, dict[str, Any]] = {}

    fixture_files = sorted((data / "fixture-inputs").glob("*.json"))
    stress_files = sorted((data / "stress-inputs").glob("*.json"))
    grammar_files = sorted((grammar_data / "inputs").glob("*.json"))
    if (len(fixture_files), len(stress_files), len(grammar_files)) != (80, 300, 400):
        raise AssertionError((len(fixture_files), len(stress_files), len(grammar_files)))

    for path in fixture_files:
        match = FIXTURE_RE.fullmatch(path.stem)
        if not match:
            raise AssertionError(path.name)
        case_index = int(match.group(1))
        variant = match.group(2)
        expected = fixture_request(case_index, variant)
        row = fixture_rows[path.stem]
        request, result = check_core_request(
            path, data / "fixture-certificates" / path.name, expected, row
        )
        requests[request["id"]] = request
        core_results[request["id"]] = result

    for path in stress_files:
        match = STRESS_RE.fullmatch(path.stem)
        if not match:
            raise AssertionError(path.name)
        index = int(match.group(1)) - 1
        expected, _oracle_rows = stress_request(index)
        row = stress_rows[path.stem]
        request, result = check_core_request(
            path, data / "stress-certificates" / path.name, expected, row
        )
        requests[request["id"]] = request
        core_results[request["id"]] = result

    if len(requests) != 380 or len(core_results) != 380:
        raise AssertionError("core request count")

    compact_files = sorted((data / "refutation-witnesses").glob("*.json"))
    if len(compact_files) != 285:
        raise AssertionError(len(compact_files))
    compact_verified = 0
    for path in compact_files:
        request = requests[path.stem]
        certificate = strict_load(path)
        result = refutation_check(request, certificate)
        row = refutation_rows[path.stem]
        if not exact_equal(result["witness"], row.get("witness", core_results[path.stem]["witness"])):
            # Current rows store sizes/work rather than duplicating the witness.
            if not exact_equal(result["witness"], core_results[path.stem]["witness"]):
                raise AssertionError((path.stem, "compact witness"))
        compact_verified += 1

    grammar_compact = 0
    grammar_forged_rejections = 0
    grammar_node_counts: list[int] = []
    grammar_point_counts: list[int] = []
    for path in grammar_files:
        row = grammar_rows[path.stem]
        seed = row["seed"]
        variant = row["variant"]
        expected_request, original, candidate, reference = grammar_case(seed, variant)
        request = strict_load(path)
        assert_authoritative_request(request, expected_request, path.name)
        expected = grammar_oracle(request, original, candidate, reference)
        certificate = produce(request)
        actual = proof_check(request, certificate)
        direct = evaluate_topological(request)
        for observed in (actual, direct):
            if observed["status"] != expected["status"] or not exact_equal(observed["witness"], expected["witness"]):
                raise AssertionError((request["id"], expected, observed))
        for key, observed in (
            ("status", actual["status"]),
            ("witness", actual["witness"]),
            ("nodes", actual["checked_nodes"]),
            ("points", len(certificate["points"])),
            ("certificate_bytes", len(canonical_bytes(certificate))),
        ):
            if not exact_equal(row[key], observed):
                raise AssertionError((request["id"], key, row[key], observed))
        if actual["status"] == "REFUTED":
            witness = produce_refutation(request, actual["witness"])
            compact = refutation_check(request, witness)
            if not exact_equal(compact["witness"], expected["witness"]):
                raise AssertionError((request["id"], "grammar compact"))
            grammar_compact += 1
        else:
            first = [request["inputs"][name][0] for name in request["inputs"]]
            forged = produce_refutation(
                request, {"obligation": "defined", "trace": [], "input": first}
            )
            try:
                refutation_check(request, forged)
            except (Invalid, Unsupported):
                grammar_forged_rejections += 1
            else:
                raise AssertionError((request["id"], "forged compact accepted"))
        grammar_node_counts.append(actual["checked_nodes"])
        grammar_point_counts.append(len(certificate["points"]))

    all_ids = sorted([*requests, *grammar_rows])
    if len(all_ids) != 780 or len(set(all_ids)) != 780:
        raise AssertionError("780-request disk population")
    id_digest = hashlib.sha256(canonical_bytes(all_ids)).hexdigest()
    point_distribution = {
        str(value): grammar_point_counts.count(value) for value in sorted(set(grammar_point_counts))
    }
    result = {
        "schema": "disk-replay-audit-v1",
        "outcome": "PASS",
        "request_files_reloaded": 780,
        "fixture_requests_reloaded": 80,
        "stress_requests_reloaded": 300,
        "grammar_requests_reloaded": 400,
        "full_vector_certificates_validated": 380,
        "compact_refutation_certificates_validated": compact_verified,
        "grammar_results_validated": 400,
        "grammar_compact_refutations_validated": grammar_compact,
        "grammar_forged_refutations_rejected": grammar_forged_rejections,
        "grammar_point_distribution": point_distribution,
        "grammar_node_range": [min(grammar_node_counts), max(grammar_node_counts)],
        "grammar_median_nodes": statistics.median(grammar_node_counts),
        "authoritative_order_source": (
            "fixture/stress generators and retained grammar seeds; no certificate field is used "
            "to choose request coordinate order"
        ),
        "request_id_index_sha256": id_digest,
        "wall_seconds": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
