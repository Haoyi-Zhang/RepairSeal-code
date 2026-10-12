"""Paired full-vector/no-certificate timings under the same finite obligations.

Only the 20 supplied correct fixtures are used. The timed boundary starts with
decoded requests/certificates; it includes reconstruction and certificate hashing
but excludes file I/O, decoding, and production. These descriptive measurements
are not a new correctness proof or a compact/full guarantee comparison.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fixture_oracle import request as fixture_request
from proof_dag_checker import check, evaluate_topological, exact_equal, load_json_strict


def describe(values):
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return {"median": statistics.median(values), "p25": quartiles[0], "p75": quartiles[2]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must not exist")
    inputs = []
    full_cells = direct_cells = 0
    for case in range(1, 21):
        expected = fixture_request(case, "correct")
        name = expected["id"] + ".json"
        request = load_json_strict((ROOT / "proof-data" / "fixture-inputs" / name).read_text())
        if list(request["inputs"]) != list(expected["inputs"]) or not exact_equal(request, expected):
            raise AssertionError((name, "authoritative request differs"))
        certificate = load_json_strict((ROOT / "proof-data" / "fixture-certificates" / name).read_text())
        full = check(request, certificate)
        direct = evaluate_topological(request)
        if full["status"] != "ACCEPT" or direct["status"] != "ACCEPT":
            raise AssertionError(name)
        if full["checked_cells"] != direct["checked_cells"]:
            raise AssertionError((name, "cell-work mismatch"))
        full_cells += full["checked_cells"]
        direct_cells += direct["checked_cells"]
        inputs.append((request, certificate))
    if full_cells != 45198 or direct_cells != 45198:
        raise AssertionError((full_cells, direct_cells))
    rows = []
    paired_ratios = []
    for repeat in range(10):
        for index, (request, certificate) in enumerate(inputs):
            calls = {"full_vector": lambda: check(request, certificate),
                     "topological_direct": lambda: evaluate_topological(request)}
            order = list(calls)
            if (repeat + index) % 2:
                order.reverse()
            elapsed = {}
            for method in order:
                start = time.perf_counter_ns()
                result = calls[method]()
                elapsed[method] = (time.perf_counter_ns() - start) / 1e6
                if result["status"] != "ACCEPT" or result["witness"] is not None:
                    raise AssertionError((request["id"], result))
                rows.append({"id": request["id"], "repeat": repeat, "method": method,
                             "milliseconds": elapsed[method]})
            paired_ratios.append(elapsed["full_vector"] / elapsed["topological_direct"])
    result = {"schema": "paired-receiver-timing-v1", "outcome": "PASS",
              "python_version": platform.python_version(), "platform": platform.platform(),
              "fixtures": 20, "repetitions": 10, "samples_per_method": 200,
              "full_vector_cells": full_cells, "topological_direct_cells": direct_cells,
              "timing_ms": {method: describe([row["milliseconds"] for row in rows if row["method"] == method])
                            for method in ("full_vector", "topological_direct")},
              "median_paired_full_over_direct": statistics.median(paired_ratios),
              "measurement_boundary": "Decoded inputs; API calls include reconstruction and hashing, exclude decoding/I/O/production.",
              "order": "Alternating first method by fixture index and repetition.", "records": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2))


if __name__ == "__main__":
    main()
