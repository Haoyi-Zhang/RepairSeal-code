"""Artifact-local portable membership conformance for P004.

Uses the independent product-enumerating test reference.
Full-certificate checks use the current full receiver plus retained manifests
and the strong topological path.

Only reviewed local Python modules and benign finite-fragment data are used.
No experiment/security/native drivers, subprocesses, clocks or file writes.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
ARTIFACT = Path(__file__).resolve().parents[1]
MASK = (1 << 32) - 1
STATS = Counter()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_engine(kind):
    root = ARTIFACT
    core = load_module("_p004_local_" + kind + "_full", root / "src" / "proof_dag_checker.py")
    path = (root / "tests" / "product_membership_reference.py" if kind == "reference"
            else root / "src" / "refutation_witness_checker.py")
    with patch.dict(sys.modules, {"proof_dag_checker": core}):
        compact = load_module("_p004_local_" + kind + "_compact", path)
    if kind == "reference":
        # Only admission/enumeration is independently implemented. The rest of
        # this namespace names the shared current proof semantics explicitly.
        full = SimpleNamespace(**vars(core))
        full.validate_request = compact.validate_request
    else:
        full = core
    return SimpleNamespace(root=root, full=full, compact=compact)


def load_pair():
    return load_engine("reference"), load_engine("current")


def strict_file(engine, path):
    return engine.full.load_json_strict(path.read_text(encoding="utf-8"))


def outcome(engine, action):
    try:
        return ("ok", action())
    except (engine.full.Invalid, engine.full.Unsupported) as exc:
        return ("error", type(exc).__name__, str(exc))


def equal(left, right, context):
    # JSON type equality matters: never rely on bool == int.
    if type(left) is not type(right):
        raise AssertionError((context, "type mismatch", left, right))
    if type(left) is dict:
        if set(left) != set(right):
            raise AssertionError((context, "keys", left, right))
        for key in left:
            equal(left[key], right[key], (context, key))
    elif type(left) in {tuple, list}:
        if len(left) != len(right):
            raise AssertionError((context, "length", left, right))
        for index, (a, b) in enumerate(zip(left, right)):
            equal(a, b, (context, index))
    elif left != right:
        raise AssertionError((context, left, right))


def rehash(full, packet):
    packet.pop("certificate_sha256", None)
    import hashlib
    packet["certificate_sha256"] = hashlib.sha256(full.canonical_bytes(packet)).hexdigest()
    return packet


def packet_for(full, request, obligation, point, trace=None):
    packet = {
        "kind": "finite-semantic-refutation-v1", "request_id": request["id"],
        "word_bits": request["word_bits"], "input_order": list(request["inputs"]),
        "domains": copy.deepcopy(request["inputs"]),
        "source_sha256": {role: full.digest(request[role]) for role in (*full.ROLES, "repair_guard")},
        "obligation": obligation, "input": copy.deepcopy(point),
        "trace": [] if trace is None else copy.deepcopy(trace),
    }
    return rehash(full, packet)


def synthetic_request(domains, obligation="repair", identifier="coordinate-regression"):
    names = list(domains)
    signature = ", ".join("unsigned " + name for name in names)
    zero = "unsigned f(" + signature + ") { return 0u; }\n"
    one = "unsigned f(" + signature + ") { return 1u; }\n"
    # Undefined operations are interpreted as data only, never run as native C.
    undefined = "unsigned f(" + signature + ") { return 1u / 0u; }\n"
    return {
        "id": identifier, "word_bits": 32, "inputs": copy.deepcopy(domains),
        "original": zero, "candidate": undefined if obligation == "defined" else one,
        "reference": zero,
        "repair_guard": names[0] + (" != " if obligation == "preserve" else " == ") + names[0],
    }


def valid_domains():
    return [
        ("singleton", {"x": [MASK]}),
        ("authoritative-z-a", {"z": [0, 3], "a": [1, 7]}),
        ("word-endpoints", {"x": [0, (1 << 31), MASK], "y": [0, 1, MASK]}),
        ("original-four-inputs", {n: [0, 1, 3] for n in ("x", "y", "z", "t")}),
        ("mixed", {"q": [0, 3, MASK], "b": [1, 7], "a": [2]}),
        ("domain-64", {"x": list(range(64))}),
        ("domain-64x64", {"x": list(range(64)), "y": list(range(64))}),
        ("eight-inputs", {f"x{i}": [0, 1] for i in range(8)}),
        ("eight-inputs-4096", {f"x{i}": list(range(4)) if i < 6 else [0] for i in range(8)}),
    ]


def compact_pair(reference, current, request, packet, expected=None):
    before = copy.deepcopy((request, packet))
    counts = []
    results = []
    for engine in (reference, current):
        counter = Counter()
        result = outcome(engine, lambda: engine.compact.check(
            request, packet, lambda category, n=1: counter.update({category: n})))
        results.append(result)
        counts.append(dict(counter))
    equal(results[0], results[1], "compact result including reason/format")
    equal(counts[0], counts[1], "scientific semantic counters")
    equal((request, packet), before, "input objects not mutated")
    if expected is not None:
        equal(results[0][0], expected, "expected outcome")
    if results[0][0] == "ok":
        cells = results[0][1]["checked_cells"]
        equal(cells, results[0][1]["checked_nodes"], "N semantic cells")
        equal(counts[0], {"refutation_cells": cells}, "unchanged counter label/count")
    STATS["compact_reference_current_pairs"] += 1
    return results[0]


def retained_pair(reference, current, identifier):
    population = "fixture" if identifier.startswith("fixture-") else "stress"
    data = reference.root / "proof-data"
    request = strict_file(reference, data / (population + "-inputs") / (identifier + ".json"))
    packet = strict_file(reference, data / "refutation-witnesses" / (identifier + ".json"))
    return request, packet


class CoordinateRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference, cls.current = load_pair()

    def test_valid_admission_and_canonical_points(self):
        for label, domains in valid_domains():
            request = synthetic_request(domains, identifier=label)
            reference = self.reference.full.validate_request(request)
            current = self.current.full.validate_request(request)
            equal(reference, current, label)
            equal(self.current.full.validate_request_fields(request), reference[:2], label)
            self.assertIs(self.current.full.validate_request_fields(request)[0], request["inputs"])
            equal(reference[1], list(domains), "authoritative insertion order")
            equal(len(reference[2]), math.prod(map(len, domains.values())), "product count")
            STATS["valid_admission_domains"] += 1

    def test_malformed_request_admission_and_error_precedence(self):
        base = synthetic_request({"x": [0, 1], "y": [0, 1]})
        cases = [("not-dict", []), ("dict-subclass", type("RequestSubclass", (dict,), {})(base))]
        def changed(label, field, value):
            req = copy.deepcopy(base)
            req[field] = value
            cases.append((label, req))
        req = copy.deepcopy(base); req["extra"] = 0; cases.append(("extra", req))
        req = copy.deepcopy(base); del req["reference"]; cases.append(("missing", req))
        for value in ("", 1, "x" * 65):
            changed("identifier-" + repr(value), "id", value)
        for value in (True, 64, "32"):
            changed("width-" + repr(value), "word_bits", value)
        for value in ([], {}, {f"x{i}": [0] for i in range(9)},
                      type("DomainsSubclass", (dict,), {})({"x": [0]})):
            changed("input-schema-" + repr(value), "inputs", value)
        for name in ("if", "__x", "_X", "bad-name", 1):
            changed("input-name-" + repr(name), "inputs", {name: [0]})
        for values in ([], (), [False, 1], [0, True], [1.0], [None], [[]], [{}],
                       [-1, 0], [0, MASK + 1], [0, 0], [1, 0], list(range(65)),
                       type("DomainSubclass", (list,), {})([0, 1]),
                       [type("IntSubclass", (int,), {})(1)]):
            changed("domain-" + repr(values), "inputs", {"x": values})
        changed("product-over-cap", "inputs", {"x": list(range(64)), "y": list(range(64)), "z": [0, 1]})
        for field in (*self.reference.full.ROLES, "repair_guard"):
            changed("source-type-" + field, field, None)
        # Product admission must still precede source-type rejection.
        req = copy.deepcopy(base)
        req["inputs"] = {"x": list(range(64)), "y": list(range(64)), "z": [0, 1]}
        req["candidate"] = None
        cases.append(("multiple-fault-precedence", req))
        for label, request in cases:
            reference = outcome(self.reference, lambda: self.reference.full.validate_request(request))
            current = outcome(self.current, lambda: self.current.full.validate_request(request))
            fields = outcome(self.current, lambda: self.current.full.validate_request_fields(request))
            equal(reference, current, label)
            equal(reference, fields, label)
            self.assertEqual(reference[0], "error", label)
            # A valid packet cannot redefine a malformed authoritative request.
            packet = packet_for(self.reference.full, base, "repair", [0, 0])
            compact_pair(self.reference, self.current, request, packet, "error")
            STATS["malformed_admission_requests"] += 1

    def test_membership_equivalence_and_real_checker_paths(self):
        for label, domains in valid_domains():
            request = synthetic_request(domains, identifier=label)
            _, names, points = self.reference.full.validate_request(request)
            candidates = list(points)
            for index in range(len(names)):
                missing = copy.deepcopy(points[0])
                missing[index] = MASK + 1
                candidates.append(missing)
            # Exhaustive finite Cartesian-vs-coordinate identity, not a timer.
            for point in candidates:
                equal(point in points, all(v in domains[n] for n, v in zip(names, point)), label)
                STATS["finite_membership_identity_pairs"] += 1
            # Exercise production check functions, not just the mathematical identity.
            chosen = points if len(points) <= 81 else [points[0], points[len(points) // 2], points[-1]]
            for point in chosen:
                packet = packet_for(self.reference.full, request, "repair", point)
                compact_pair(self.reference, self.current, request, packet, "ok")
                STATS["production_in_domain_pairs"] += 1
            for index in range(len(names)):
                point = copy.deepcopy(points[0]); point[index] = MASK + 1
                result = compact_pair(self.reference, self.current, request,
                                      packet_for(self.reference.full, request, "repair", point), "error")
                equal(result[2], "refutation input outside domain", label)
                STATS["production_outside_domain_pairs"] += 1

    def test_point_types_lengths_and_membership_do_not_define_input_order(self):
        request = synthetic_request({"z": [0, 3], "a": [1, 7]})
        for point in ([False, 1], [True, 1], [0.0, 1], [None, 1], [[0], 1],
                      [0], [0, 1, 7], (0, 1), "01", [1, 0]):
            packet = packet_for(self.reference.full, request, "repair", point)
            compact_pair(self.reference, self.current, request, packet, "error")
            STATS["malformed_points"] += 1
        packet = packet_for(self.reference.full, request, "repair", [0, 1])
        packet["input_order"] = ["a", "z"]
        rehash(self.reference.full, packet)
        result = compact_pair(self.reference, self.current, request, packet, "error")
        equal(result[2], "refutation request/domain binding", "order not certificate-owned")

    def test_compact_avoids_cartesian_generation_without_reducing_semantics(self):
        request, packet = retained_pair(self.reference, self.current, "fixture-01-overfit")
        baseline = self.current.compact.check(request, packet)
        with patch.object(self.current.full.itertools, "product", side_effect=AssertionError("Cartesian generator called")):
            counter = Counter()
            result = self.current.compact.check(request, packet, lambda k, n=1: counter.update({k: n}))
            equal(result, baseline, "no allocation, exact result")
            equal(dict(counter), {"refutation_cells": baseline["checked_nodes"]}, "still N cells")
            with self.assertRaises(AssertionError):
                self.current.full.validate_request(request)
        with patch.object(self.reference.compact.itertools, "product",
                          side_effect=AssertionError("reference product required")):
            with self.assertRaisesRegex(AssertionError, "reference product required"):
                self.reference.compact.check(request, packet)
        STATS["no_cartesian_compact_checks"] += 1

    def test_retained_core_packets_full_proof_and_counter_conformance(self):
        data = self.reference.root / "proof-data"
        full_records = []
        for population in ("fixture", "stress"):
            rows = strict_file(self.reference, data / (population + "-cases.json"))
            for row in rows:
                request = strict_file(self.reference, data / (population + "-inputs") / (row["id"] + ".json"))
                cert_path = Path(population + "-certificates") / (row["id"] + ".json")
                certificate = strict_file(self.current, data / cert_path)
                before = copy.deepcopy((request, certificate))
                counter = Counter()
                result = self.current.full.check(request, certificate,
                    lambda k, n=1: counter.update({k: n}))
                equal((request, certificate), before, "full objects preserved")
                equal(result["witness"], row["witness"], row["id"])
                equal(result["status"], row["status"], row["id"])
                cells = row["nodes"] * row["points"]
                equal(dict(counter), {"proof_cells": cells}, row["id"])
                equal(result["checked_cells"], cells, row["id"])
                counter = Counter()
                direct = self.current.full.evaluate_topological(request, lambda k, n=1: counter.update({k: n}))
                equal(direct["status"], result["status"], row["id"])
                equal(direct["witness"], result["witness"], row["id"])
                equal(dict(counter), {"topological_cells": cells}, row["id"])
                STATS["full_semantic_cells_current"] += cells
                STATS["retained_full_certificates"] += 1
                if population == "fixture" and row["variant"] == "correct":
                    STATS["correct_fixture_semantic_cells_current"] += cells
                full_records.append(row["id"])
        equal(len(full_records), 380, "bounded frozen core")
        packets = sorted((data / "refutation-witnesses").glob("*.json"))
        equal(len(packets), 285, "bounded frozen compact core")
        for path in packets:
            request, packet = retained_pair(self.reference, self.current, path.stem)
            result = compact_pair(self.reference, self.current, request, packet, "ok")
            STATS["retained_compact_certificates"] += 1
            STATS["retained_compact_semantic_cells_per_arm"] += result[1]["checked_cells"]

    def test_binding_diagnostics_and_definedness_preserved(self):
        request, original = retained_pair(self.reference, self.current, "fixture-01-overfit")
        cases = []
        def change(label, action, reason):
            packet = copy.deepcopy(original); action(packet); rehash(self.reference.full, packet)
            cases.append((label, packet, reason))
        change("extra", lambda p: p.update(extra=0), "refutation certificate schema")
        change("request-id", lambda p: p.update(request_id="different"), "refutation request/domain binding")
        change("word-bool", lambda p: p.update(word_bits=True), "refutation request/domain binding")
        change("domain-narrowing", lambda p: p["domains"].update(x=[0, 1]), "refutation request/domain binding")
        change("source-binding", lambda p: p["source_sha256"].update(candidate="0" * 64), "refutation source binding")
        change("unknown-obligation", lambda p: p.update(obligation="other"), "refutation obligation")
        change("true-obligation", lambda p: p.update(obligation="defined"), "claimed obligation is true")
        change("trace-type", lambda p: p.update(trace="not-trace"), "refutation trace")
        change("trace-content", lambda p: p.update(trace=[]), "refutation trace mismatch")
        stale = copy.deepcopy(original); stale["request_id"] = "different"
        cases.append(("stale", stale, "refutation digest"))
        for label, packet, reason in cases:
            result = compact_pair(self.reference, self.current, request, packet, "error")
            equal(result[2], reason, label)
            STATS["compact_binding_controls"] += 1
        # Conservative selector admission must not be relaxed by field validation.
        guard_req = synthetic_request({"x": [0, 1, 2]})
        guard_req["repair_guard"] = "(x == 0u) || ((1u / x) > 0u)"
        result = compact_pair(self.reference, self.current, guard_req,
                              packet_for(self.reference.full, guard_req, "repair", [0]), "error")
        equal(result[2], "guard totality not simplified to true", "admission boundary")
        STATS["conservative_selector_checks"] += 1

    def test_exact_full_proof_rejections_remain_active(self):
        data = self.reference.root / "proof-data"
        request = strict_file(self.reference, data / "fixture-inputs" / "fixture-01-correct.json")
        original = strict_file(self.reference, data / "fixture-certificates" / "fixture-01-correct.json")
        cases = []
        for field, value in (("guard_root", -1), ("points", []), ("extra", 0)):
            cert = copy.deepcopy(original); cert[field] = value
            cases.append((field, rehash(self.reference.full, cert)))
        cert = copy.deepcopy(original); cert["nodes"][0]["vector"][0] = not cert["nodes"][0]["vector"][0]
        cases.append(("local-vector", rehash(self.reference.full, cert)))
        cert = copy.deepcopy(original); cert["nodes"][0]["id"] = True
        cases.append(("typed-topology", rehash(self.reference.full, cert)))
        cert = copy.deepcopy(original); cert["source_sha256"]["candidate"] = "0" * 64
        cases.append(("source", rehash(self.reference.full, cert)))
        for label, cert in cases:
            after = outcome(self.current, lambda: self.current.full.check(request, cert))
            reasons = {
                "guard_root": "root binding", "points": "request/domain binding",
                "extra": "certificate schema", "local-vector": "node 0 cell 0 mismatch",
                "typed-topology": "node 0 topology", "source": "source binding",
            }
            equal(after, ("error", "Invalid", reasons[label]), label)
            STATS["full_binding_local_controls"] += 1


def main():
    # TestResult avoids TextTestRunner's elapsed-time measurement/report.
    result = unittest.TestResult()
    asset_root = ARTIFACT.resolve()
    def guarded(reader):
        def read(path, *args, **kwargs):
            if not path.resolve().is_relative_to(asset_root):
                raise AssertionError("regression asset outside standalone artifact")
            return reader(path, *args, **kwargs)
        return read
    # Data may not silently come from a private snapshot or delivery checkout.
    # Python/stdlib module loading remains the ordinary trusted runtime.
    with patch.object(Path, "read_text", guarded(Path.read_text)), \
         patch.object(Path, "read_bytes", guarded(Path.read_bytes)):
        unittest.defaultTestLoader.loadTestsFromTestCase(CoordinateRegression).run(result)
    report = {
        "outcome": "PASS" if result.wasSuccessful() else "FAIL",
        "tests_run": result.testsRun, "checks": dict(sorted(STATS.items())),
        "comparison": "product-enumerating test reference versus current compact receiver",
        "regression_asset_read_scope": "standalone artifact only",
        "timing_performed": False, "grammar_campaign_rerun": False,
        "security_or_reproduction_driver_run": False,
        "failures": result.failures, "errors": result.errors,
        "python": sys.version.split()[0],
    }
    print(json.dumps(report, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
