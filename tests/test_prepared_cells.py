"""Portable finite conformance checks for prepared full-vector cell operands.

The arithmetic reference below is literal test-local mathematics, not a copied
checker. It does not independently validate the entire source frontend. No
native compiler, subprocess, network, clock, or file-output operation is used.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import sys
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
ARTIFACT = Path(__file__).resolve().parents[1]
MODULUS = 2 ** 32
STATS = Counter()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_engine(artifact=ARTIFACT, label="current"):
    full = load_module("_cells_" + label + "_full", artifact / "src/proof_dag_checker.py")
    producer = load_module("_cells_" + label + "_producer", artifact / "src/producer.py")
    with patch.dict(sys.modules, {"producer": producer}):
        dag = load_module("_cells_" + label + "_dag", artifact / "src/proof_dag_producer.py")
    with patch.dict(sys.modules, {"proof_dag_checker": full}):
        compact = load_module("_cells_" + label + "_compact", artifact / "src/refutation_witness_checker.py")
    with patch.dict(sys.modules, {"proof_dag_producer": dag}):
        pack = load_module("_cells_" + label + "_pack", artifact / "src/refutation_witness_producer.py")
    return SimpleNamespace(root=artifact, full=full, dag=dag, compact=compact, pack=pack)


def equal(left, right, label):
    if type(left) is not type(right):
        raise AssertionError((label, "type", left, right))
    if type(left) is dict:
        if set(left) != set(right):
            raise AssertionError((label, "keys"))
        for key in left:
            equal(left[key], right[key], (label, key))
    elif type(left) in {list, tuple}:
        if len(left) != len(right):
            raise AssertionError((label, "length"))
        for a, b in zip(left, right):
            equal(a, b, label)
    elif left != right:
        raise AssertionError((label, left, right))


def reference(op, args):
    """Independent primitive formulas, including totalization and exact sorts."""
    if op == "not": return not args[0]
    if op == "inv": return (MODULUS - 1) ^ args[0]
    if op == "and": return bool(args[0]) and bool(args[1])
    if op == "or": return bool(args[0]) or bool(args[1])
    if op == "ite": return args[1] if args[0] else args[2]
    a, b = args
    if op == "+": return (a + b) % MODULUS
    if op == "-": return (a - b) % MODULUS
    if op == "*": return (a * b) % MODULUS
    if op == "/": return 0 if b == 0 else a // b
    if op == "%": return 0 if b == 0 else a % b
    if op == "<<": return 0 if b >= 32 else (a * 2 ** b) % MODULUS
    if op == ">>": return 0 if b >= 32 else a // 2 ** b
    if op == "&": return a & b
    if op == "|": return a | b
    if op == "^": return a ^ b
    if op == "==": return a == b
    if op == "!=": return a != b
    if op == "<": return a < b
    if op == "<=": return a <= b
    if op == ">": return a > b
    if op == ">=": return a >= b
    raise AssertionError(("unreviewed operator", op))


def reference_vectors(request, certificate):
    names = list(request["inputs"])
    points = list(itertools.product(*request["inputs"].values()))
    vectors = []
    for node in certificate["nodes"]:
        op = node["op"]
        if op in {"b", "u"}: vector = [node["data"] for _ in points]
        elif op == "input": vector = [p[names.index(node["data"])] for p in points]
        else:
            vector = [reference(op, [vectors[c][i] for c in node["children"]])
                      for i in range(len(points))]
        equal(node["vector"], vector, (request["id"], node["id"]))
        vectors.append(vector)
    return vectors


def request_for(identifier, body, domains=None, original=None, reference_body=None, guard="z == 0u"):
    axes = domains if domains is not None else {"z": [0, 1, 2147483648, 4294967295], "a": [0, 1, 31, 32]}
    signature = ", ".join("unsigned " + n for n in axes)
    def source(text): return "unsigned f(" + signature + ") { " + text + " }\n"
    return {"id": identifier, "word_bits": 32, "inputs": copy.deepcopy(axes),
            "original": source(original if original is not None else body),
            "candidate": source(body), "reference": source(reference_body if reference_body is not None else body),
            "repair_guard": guard}


def tiny_requests():
    requests = []
    for index, op in enumerate(("+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^")):
        requests.append(request_for("arithmetic-" + str(index), "return z " + op + " a;"))
    requests.append(request_for("complement", "return ~z;"))
    for index, condition in enumerate(("z == a", "z != a", "z < a", "z <= a", "z > a", "z >= a",
                                       "!(z == a)", "(z == 0u) && (a != 0u)",
                                       "(z == 0u) || (a != 0u)")):
        requests.append(request_for("condition-" + str(index),
            "unsigned r = z; if (" + condition + ") { r = z + a; } else { r = z - a; } return r;"))
    return requests


def counted(engine, request, certificate, mode="proof"):
    counts = Counter()
    result = engine.full.check(request, certificate, lambda k, n=1: counts.update({k: n}), mode=mode)
    return result, dict(counts)


def rehash(packet):
    packet.pop("certificate_sha256", None)
    encoded = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    packet["certificate_sha256"] = hashlib.sha256(encoded).hexdigest()
    return packet


class PreparedCells(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.engine = load_engine()

    def test_literal_math_all_circuit_tags(self):
        seen = set()
        for request in tiny_requests():
            certificate = self.engine.dag.produce(request)
            vectors = reference_vectors(request, certificate)
            seen.update(n["op"] for n in certificate["nodes"])
            result, counts = counted(self.engine, request, certificate)
            cells = len(vectors) * len(certificate["points"])
            equal(counts, {"proof_cells": cells}, request["id"])
            direct = self.engine.full.evaluate_topological(request)
            equal((result["status"], result["witness"], result["checked_cells"]),
                  (direct["status"], direct["witness"], direct["checked_cells"]), request["id"])
            STATS["literal_cases"] += 1
            STATS["literal_cells"] += cells
        equal(seen, {"b", "u", "input", "inv", "+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^",
                     "not", "and", "or", "==", "!=", "<", "<=", ">", ">=", "ite"}, "all 24 tags")

    def test_truth_and_trace_priority_not_numeric_priority(self):
        axes = {"z": [0, 1], "a": [0, 1]}
        branch = "unsigned r = 0u; if (z == 0u) { r = 1u; } else { r = 1u; } return r;"
        for obligation, guard in (("repair", "a == 0u"), ("preserve", "a != 0u")):
            request = request_for("trace-" + obligation, branch, axes,
                                  original="return 0u;", reference_body="return 1u;" if obligation=="preserve" else "return 0u;", guard=guard)
            certificate = self.engine.dag.produce(request)
            result, _counts = counted(self.engine, request, certificate)
            expected = {"obligation": obligation, "trace": [[0, 0]], "input": [1, 0]}
            equal(result["witness"], expected, obligation)
            # An authentic nonleast point is still a valid existential witness.
            hint = {"obligation": obligation, "trace": [[0, 1]], "input": [0, 0]}
            packet = self.engine.pack.produce(request, hint)
            equal(self.engine.compact.check(request, packet)["witness"], hint, "nonleast compact")
            wrong = copy.deepcopy(packet); wrong["trace"] = []; rehash(wrong)
            with self.assertRaisesRegex(self.engine.full.Invalid, "refutation trace mismatch"):
                self.engine.compact.check(request, wrong)
        body = "unsigned poison = 1u / a; " + branch
        request = request_for("trace-stops", body, axes)
        equal(counted(self.engine, request, self.engine.dag.produce(request))[0]["witness"],
              {"obligation": "defined", "trace": [], "input": [0, 0]}, "undefined prefix")
        STATS["literal_trace_cases"] += 3

    def test_retained_core_and_exact_counters(self):
        data = self.engine.root / "proof-data"
        for population in ("fixture", "stress"):
            rows = self.engine.full.load_json_strict((data / (population + "-cases.json")).read_text(encoding="utf-8"))
            for row in rows:
                req = self.engine.full.load_json_strict((data / (population + "-inputs") / (row["id"] + ".json")).read_text(encoding="utf-8"))
                cert = self.engine.full.load_json_strict((data / (population + "-certificates") / (row["id"] + ".json")).read_text(encoding="utf-8"))
                untouched = copy.deepcopy((req, cert))
                result, counts = counted(self.engine, req, cert)
                equal((req, cert), untouched, "immutable input")
                equal((result["status"], result["witness"]), (row["status"], row["witness"]), row["id"])
                equal(counts, {"proof_cells": row["nodes"] * row["points"]}, row["id"])
                STATS["retained_full"] += 1
                STATS["retained_full_cells"] += result["checked_cells"]
        equal(STATS["retained_full"], 380, "core count")
        equal(STATS["retained_full_cells"], 1179684, "core scientific cells")

    def test_each_cell_checks_types_values_and_stopping_counter(self):
        req = tiny_requests()[12]
        original = self.engine.dag.produce(req)
        prior = 0
        for node in original["nodes"]:
            for cell in (0, len(original["points"]) - 1):
                for kind in ("type", "value"):
                    cert = copy.deepcopy(original)
                    old = cert["nodes"][node["id"]]["vector"][cell]
                    value = (int(old) if type(old) is bool else bool(old)) if kind == "type" else (not old if type(old) is bool else (old + 1) % MODULUS)
                    cert["nodes"][node["id"]]["vector"][cell] = value
                    rehash(cert)
                    counter = Counter()
                    reason = (f"node {node['id']} sort" if kind == "type" else f"node {node['id']} cell {cell} mismatch")
                    with self.assertRaisesRegex(self.engine.full.Invalid, "^" + reason + "$"):
                        self.engine.full.check(req, cert, lambda k, n=1: counter.update({k: n}))
                    equal(dict(counter), {"proof_cells": prior + cell + 1}, "early rejection count")
                    STATS["cell_negative_controls"] += 1
            prior += len(original["points"])
        class Stop(RuntimeError): pass
        visits = []
        def stop(kind, n):
            visits.append((kind, n))
            if len(visits) == 7: raise Stop("seven")
        with self.assertRaises(Stop): self.engine.full.check(req, original, stop)
        equal(visits, [("proof_cells", 1)] * 7, "callback deadline boundary")

    def test_rebuild_and_domain_bound_preserved(self):
        req = request_for("4096-bound", "return z + a;", {"z": list(range(64)), "a": list(range(64))})
        cert = self.engine.dag.produce(req)
        proof, proof_counts = counted(self.engine, req, cert)
        rebuilt, rebuild_counts = counted(self.engine, req, cert, mode="rebuild")
        equal((proof["status"], proof["witness"], proof["checked_cells"]),
              (rebuilt["status"], rebuilt["witness"], rebuilt["checked_cells"]), "rebuild")
        equal(rebuild_counts["proof_cells"], proof_counts["proof_cells"], "outer NM cells")
        self.assertGreater(rebuild_counts["rebuild_cells"], 0)
        over = copy.deepcopy(req); over["inputs"]["b"] = [0, 1]
        with self.assertRaisesRegex(self.engine.full.Unsupported, "domain bound"):
            self.engine.full.check(over, cert)
        STATS["boundary_points"] = 4096


def main():
    result = unittest.TestResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(PreparedCells).run(result)
    print(json.dumps({"outcome": "PASS" if result.wasSuccessful() else "FAIL", "tests_run": result.testsRun,
                      "checks": dict(STATS), "failures": result.failures, "errors": result.errors,
                      "timing_performed": False, "full_campaign_rerun": False}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__": raise SystemExit(main())
