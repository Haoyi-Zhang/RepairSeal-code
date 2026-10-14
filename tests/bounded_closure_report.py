"""Portable replay of owned retained evidence; no native or network execution.

This reporting workflow supplements historical campaigns without overwriting
them. It replays the 380 stored full certificates and 285 compact packets,
checks the 400 grammar requests against their source generators (not a new
400-case semantic campaign), and records the two existing portable suites.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import platform
import sys
import unittest
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
from fixture_oracle import request as fixture_request, exhaustive, least_violation
from structured_study import stress_request, oracle_witness
from holdout_differential import case, BOUNDARY_VALUES
from proof_dag_checker import check, evaluate_topological, load_json_strict
from refutation_witness_checker import check as compact_check
from test_boundary_selection import BoundarySelectionTests
from test_prepared_cells import PreparedCells, STATS
from test_cli_utf8 import CliUtf8Tests
from test_driver_optimization import OptimizedDriverTests


def binding(path):
    data = path.read_bytes()
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def load(path):
    return load_json_strict(path.read_text(encoding="utf-8"))


def require_equal(actual, expected, label):
    # Canonical JSON distinguishes integer/Boolean cells that Python equates.
    def encoded(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if encoded(actual) != encoded(expected):
        raise AssertionError(label)


def run_suite(cls):
    names = unittest.defaultTestLoader.getTestCaseNames(cls)
    result = unittest.TestResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(cls).run(result)
    if not result.wasSuccessful() or result.testsRun != len(names):
        raise AssertionError((cls.__name__, result.failures, result.errors))
    return {"outcome": "PASS", "tests_run": result.testsRun,
            "methods": names, "native_execution": False}


def save(directory, name, value):
    (directory / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error("output directory must not exist")
    # Do not let scientific reports pollute the immutable input/certificate corpus.
    protected = [ROOT / "inputs", ROOT / "proof-data", ROOT / "public-data", ROOT / "src", ROOT / "tests"]
    if any(out == path or path in out.parents for path in protected):
        parser.error("output must be outside protected source/input trees")
    out.mkdir(parents=True)
    start = datetime.now(timezone.utc).isoformat()
    boundary = run_suite(BoundarySelectionTests)
    prepared = run_suite(PreparedCells)
    cli_encoding = run_suite(CliUtf8Tests)
    driver_optimization = run_suite(OptimizedDriverTests)
    prepared["checks"] = dict(STATS)
    prepared["timing_performed"] = False
    records = []
    cells = correct_cells = compact_count = 0
    status_counts = Counter()
    for population in ("fixture", "stress"):
        data = ROOT / "proof-data"
        for index, retained in enumerate(load(data / (population + "-cases.json"))):
            identifier = retained["id"]
            request_path = data / (population + "-inputs") / (identifier + ".json")
            cert_path = data / (population + "-certificates") / (identifier + ".json")
            request, cert = load(request_path), load(cert_path)
            if population == "fixture":
                expected_request = fixture_request(retained["case"], retained["variant"])
                witness = least_violation(exhaustive(retained["case"], retained["variant"]))
            else:
                expected_request, oracle_rows = stress_request(index)
                witness = oracle_witness(oracle_rows)
            require_equal(request, expected_request, identifier + " authoritative input")
            require_equal(list(request["inputs"]), list(expected_request["inputs"]), identifier + " coordinate order")
            expected = {"status": "ACCEPT" if witness is None else "REFUTED", "witness": witness}
            full, direct = check(request, cert), evaluate_topological(request)
            semantic = lambda result: {key: result[key] for key in ("status", "witness")}
            require_equal(semantic(full), expected, identifier + " full/oracle")
            require_equal(semantic(direct), expected, identifier + " direct/oracle")
            expected_cells = len(cert["nodes"]) * len(cert["points"])
            if full["checked_cells"] != direct["checked_cells"] or full["checked_cells"] != expected_cells:
                raise AssertionError(identifier + " equal cell accounting")
            compact = None
            if witness is not None:
                packet_path = data / "refutation-witnesses" / (identifier + ".json")
                compact = compact_check(request, load(packet_path))
                require_equal(compact["witness"], witness, identifier + " compact witness")
                compact_count += 1
            else:
                if population == "fixture": correct_cells += full["checked_cells"]
            records.append({"id": identifier, "population": population,
                            "request": binding(request_path), "certificate": binding(cert_path),
                            "input_order": list(request["inputs"]), "axes": request["inputs"],
                            "oracle": expected, "full": full, "direct": direct, "compact": compact})
            cells += full["checked_cells"]
            status_counts[full["status"]] += 1
    if (len(records), compact_count, cells, correct_cells) != (380, 285, 1179684, 45198):
        raise AssertionError("retained structured population/work mismatch")
    structured = {"schema": "owned-structured-replay-v1", "outcome": "PASS",
                  "requests": len(records), "statuses": dict(status_counts),
                  "oracle_full_direct_agreements": len(records), "compact_verified": compact_count,
                  "full_cells": cells, "direct_cells": cells,
                  "accepted_fixture_full_cells": correct_cells, "accepted_fixture_direct_cells": correct_cells,
                  "records": records, "native_execution": False, "timing_performed": False,
                  "scope": "Replay of existing owned synthetic corpus; not new independent programs, histories or native C validation."}
    grammar = ROOT / "proof-data/holdout-differential"
    grammar_rows = load(grammar / "cases.json")
    bindings = []
    axes = points = 0
    boundaries = Counter()
    for retained in grammar_rows:
        generated, *_ = case(retained["seed"], retained["variant"])
        path = grammar / "inputs" / (retained["id"] + ".json")
        request = load(path)
        require_equal(request, generated, retained["id"] + " grammar input")
        require_equal(list(request["inputs"]), list(generated["inputs"]), retained["id"] + " grammar order")
        for values in request["inputs"].values():
            if len(values) != 8 or values != sorted(set(values)) or not set(BOUNDARY_VALUES) <= set(values):
                raise AssertionError(retained["id"] + " boundary retention")
            axes += 1
            boundaries.update(map(str, BOUNDARY_VALUES))
        count = math.prod(map(len, request["inputs"].values()))
        if count != retained["points"]: raise AssertionError("grammar point count")
        points += count
        bindings.append({**binding(path), "seed": retained["seed"], "variant": retained["variant"],
                         "input_order": list(request["inputs"]), "axes": request["inputs"], "points": count})
    if (len(bindings), axes, points) != (400, 1217, 657728):
        raise AssertionError("grammar source/boundary population mismatch")
    source_check = {"schema": "owned-grammar-source-check-v1", "outcome": "PASS",
                    "requests": len(bindings), "axes": axes, "total_points": points,
                    "boundary_axis_counts": dict(boundaries), "inputs": bindings,
                    "retained_semantic_summary": binding(grammar / "summary.json"),
                    "semantic_campaign_rerun": False, "native_execution": False,
                    "scope": "Current generator-to-retained-source and boundary check; retained 400-case semantic outcomes are separate historical evidence."}
    source_paths = sorted([*ROOT.glob("src/*.py"), *[ROOT / "tests" / name for name in
                          ("bounded_closure_report.py", "fixture_oracle.py", "structured_study.py",
                           "holdout_differential.py", "test_boundary_selection.py", "test_prepared_cells.py",
                           "test_cli_utf8.py", "test_driver_optimization.py", "reproduce_all_core.py")]])
    environment = {"schema": "owned-bounded-replay-environment-v1", "started_utc": start,
                   "finished_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
                   "executable": sys.executable, "platform": platform.platform(), "argv": sys.argv,
                   "native_execution": False, "third_party_source_execution": False,
                   "network_execution": False, "source_bindings": [binding(path) for path in source_paths],
                   "scope": "Environment of this portable replay, not of historical native or timing campaigns."}
    for name, value in (("boundary-tests.json", boundary), ("prepared-cells.json", prepared),
                        ("cli-encoding-tests.json", cli_encoding), ("driver-optimization-tests.json", driver_optimization),
                        ("structured-replay.json", structured), ("grammar-source-check.json", source_check),
                        ("environment.json", environment)):
        save(out, name, value)
    print(json.dumps({"outcome": "PASS", "portable_test_methods": boundary["tests_run"] + prepared["tests_run"] + cli_encoding["tests_run"] + driver_optimization["tests_run"],
                      "structured_requests": len(records), "compact_packets": compact_count,
                      "source_bound_grammar_requests": len(bindings), "full_direct_cells": cells,
                      "accepted_fixture_full_direct_cells": correct_cells, "native_execution": False}, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
