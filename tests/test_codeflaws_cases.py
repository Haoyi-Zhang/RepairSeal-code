"""Owned finite-model regressions; no upstream sources, archives or native runs.

Wrapper strings below are synthetic admission fixtures, not Codeflaws payloads.
The offline study's report writes are captured in memory.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
import os
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import codeflaws_cases as cases
import codeflaws_source_study as study
from proof_dag_checker import (
    Invalid, OBLIGATIONS, ROLES, Reader, Unsupported, canonical_bytes, check,
    evaluate_topological, exact_equal, trace_from_vectors, validate_request_fields,
)
from proof_dag_producer import produce
from refutation_witness_checker import check as compact_check
from refutation_witness_producer import produce as compact_produce


DOMAINS = {
    "4-A": list(range(1, 61)) + [97, 98, 99, 100],
    "84-A": list(range(2, 121, 2)) + [99999994, 99999996, 99999998, 100000000],
}
EXPECTED = {
    ("4-A", "buggy"): {
        "status": "REFUTED",
        "witness": {"obligation": "repair", "trace": [[0, 1]], "input": [2]},
    },
    ("4-A", "supplied"): {"status": "ACCEPT", "witness": None},
    ("84-A", "buggy"): {
        "status": "REFUTED",
        "witness": {"obligation": "repair", "trace": [], "input": [2]},
    },
    ("84-A", "supplied"): {"status": "ACCEPT", "witness": None},
}


def mathematical_value(case, role, x):
    """Literal task formulas, independent of the model helpers and parser."""
    if case == "4-A":
        return int(x % 2 == 0 and (role == "buggy" or x > 2))
    return (3 // 2) * x if role == "buggy" else 3 * x // 2


def rehash(packet):
    packet.pop("certificate_sha256", None)
    packet["certificate_sha256"] = hashlib.sha256(canonical_bytes(packet)).hexdigest()
    return packet


class OwnedTar:
    """In-memory member double: no archive file or third-party bytes exist."""

    def __init__(self, entries):
        self.members = []
        self.payloads = {}
        self.reads = []
        for name, data, declared_size, regular in entries:
            member = SimpleNamespace(name=name, size=len(data) if declared_size is None else declared_size,
                                     isfile=lambda regular=regular: regular)
            self.members.append(member)
            self.payloads[id(member)] = data

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def __iter__(self):
        return iter(self.members)

    def extractfile(self, member):
        self.reads.append(member.name)
        return io.BytesIO(self.payloads[id(member)])


class OwnedProcesses:
    """Compiler/executable responses are generated data, never OS processes."""

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def popen(self, command, **kwargs):
        return OwnedProcess(self, command, kwargs)

    def run(self, command, **kwargs):
        command = [str(part) for part in command]
        record = {"command": command, "cwd": kwargs.get("cwd"), "input": kwargs.get("input"),
                  "timeout": kwargs.get("timeout"), "text": kwargs.get("text", False),
                  "caches": {k: kwargs.get("env", {}).get(k) for k in
                             ("ZIG_GLOBAL_CACHE_DIR", "ZIG_LOCAL_CACHE_DIR")}}
        self.calls.append(record)
        if "--version" in command:
            stage, stdout = "version", b"owned compiler fixture\n"
        elif "-dM" in command:
            stage = "macros"
            stdout = b"#define __SIZEOF_INT__ 4\n#define __INT_MAX__ 2147483647\n"
        elif "-o" in command:
            stage, stdout = "compile", b"owned compile output\n"
        else:
            stage = "execute"
            stem = Path(command[0]).stem
            case, role = stem.rsplit("-", 1)
            x = int(kwargs["input"])
            value = mathematical_value(case, role, x)
            stdout = ((b"YES" if value else b"NO") if case == "4-A" else str(value).encode("ascii")) + b"\n"
        record["stage"] = stage
        if self.fail is not None:
            replacement = self.fail(stage, record, len(self.calls))
            if isinstance(replacement, BaseException):
                raise replacement
            if replacement is not None:
                return replacement
        text = kwargs.get("text", False)
        return study.subprocess.CompletedProcess(command, 0, stdout.decode("ascii") if text else stdout,
                                                 "" if text else b"")


class OwnedProcess:
    """Pipe-compatible process double used by the real bounded capture code."""

    def __init__(self, owner, command, kwargs):
        self.returncode = None
        self.ready = threading.Event()
        self.error = None
        self.result = None
        raw = bytearray()
        self.stdin = SimpleNamespace(write=raw.extend, close=lambda: self.finish(owner, command, kwargs, bytes(raw)))
        self.stdout = self.pipe("stdout")
        self.stderr = self.pipe("stderr")

    def pipe(self, name):
        def read(size):
            if not self.ready.wait(2):
                raise OSError("owned process fixture did not receive stdin")
            return getattr(self, "_" + name).read(size)

        return SimpleNamespace(read=read, close=lambda: None)

    def finish(self, owner, command, kwargs, raw):
        try:
            self.result = owner.run(command, **{**kwargs, "input": raw})
            stdout, stderr = self.result.stdout, self.result.stderr
        except study.subprocess.TimeoutExpired as exc:
            self.error = exc
            stdout, stderr = exc.output or b"", exc.stderr or b""
        self._stdout = io.BytesIO(stdout)
        self._stderr = io.BytesIO(stderr)
        self.ready.set()

    def wait(self, timeout=None):
        if self.error is not None and timeout is not None:
            error, self.error = self.error, None
            raise error
        if self.returncode is None:
            self.returncode = self.result.returncode if self.result is not None else -9
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


class CodeflawsModelTests(unittest.TestCase):
    def test_exact_four_model_oracle_full_direct_results_and_work(self):
        self.assertEqual(set(cases.CASES), {"4-A", "84-A"})
        self.assertEqual(OBLIGATIONS, ("defined", "repair", "preserve"))
        for (case, role), expected in EXPECTED.items():
            with self.subTest(case=case, role=role):
                request = cases.request(case, role)
                before = copy.deepcopy(request)
                producer_work, full_work, direct_work = Counter(), Counter(), Counter()
                packet = produce(request, lambda k, n=1: producer_work.update({k: n}))
                full = check(request, packet, lambda k, n=1: full_work.update({k: n}))
                direct = evaluate_topological(request, lambda k, n=1: direct_work.update({k: n}))
                for result in (study.oracle(case, role), study.result_core(full),
                               study.result_core(direct)):
                    self.assertTrue(exact_equal(result, expected), (case, role, result))
                self.assertEqual(packet["points"], [[x] for x in DOMAINS[case]])
                nodes = len(packet["nodes"])
                self.assertEqual(full["checked_nodes"], nodes)
                self.assertEqual(direct["checked_nodes"], nodes)
                self.assertEqual(full["checked_cells"], nodes * 64)
                self.assertEqual(direct["checked_cells"], nodes * 64)
                self.assertEqual(producer_work["producer_vector_cells"], nodes * 64)
                self.assertEqual(dict(full_work), {"proof_cells": nodes * 64})
                self.assertEqual(dict(direct_work), {"topological_cells": nodes * 64})
                self.assertEqual(request, before)

    def test_every_finite_role_output_definedness_and_candidate_trace(self):
        for case, candidate in EXPECTED:
            request = cases.request(case, candidate)
            packet = produce(request)
            vectors = [node["vector"] for node in packet["nodes"]]
            for receiver_role, source_role in (
                ("original", "buggy"), ("candidate", candidate), ("reference", "reference"),
            ):
                with self.subTest(case=case, candidate=candidate, role=receiver_role):
                    roots = packet["role_roots"][receiver_role]
                    expected = [mathematical_value(case, source_role, x) for x in DOMAINS[case]]
                    self.assertEqual(vectors[roots["output"]], expected)
                    self.assertTrue(all(type(v) is int for v in vectors[roots["output"]]))
                    self.assertTrue(all(v is True for v in vectors[roots["defined"]]))
                    self.assertEqual([cases.value(case, source_role, x) for x in DOMAINS[case]], expected)
                    events = [(e["site"], e["reachable"], e["guard"]) for e in roots["trace_events"]]
                    for index, (x, value) in enumerate(zip(DOMAINS[case], expected)):
                        trace = [[0, value]] if case == "4-A" else []
                        self.assertEqual(trace_from_vectors(events, vectors, index), trace)
                        self.assertEqual(cases.trace(case, source_role, x), trace)

    def test_exact_domains_guards_source_roles_and_fresh_request_axes(self):
        for case, parameter, guard in (("4-A", "w", "w == 2u"), ("84-A", "n", "n == n")):
            for role in ("buggy", "supplied"):
                with self.subTest(case=case, role=role):
                    request = cases.request(case, role)
                    self.assertEqual(request["id"], "codeflaws-" + case + "-" + role)
                    self.assertEqual(request["word_bits"], 32)
                    self.assertEqual(request["inputs"], {parameter: DOMAINS[case]})
                    self.assertEqual(request["repair_guard"], guard)
                    self.assertEqual(request["original"], cases.function(case, "buggy"))
                    self.assertEqual(request["candidate"], cases.function(case, role))
                    self.assertEqual(request["reference"], cases.function(case, "reference"))
                    domains, names = validate_request_fields(request)
                    self.assertEqual(names, [parameter])
                    self.assertEqual(domains[parameter], sorted(set(domains[parameter])))
                    self.assertEqual(len(domains[parameter]), 64)
                    self.assertTrue(all(cases.legal_input(case, x) for x in domains[parameter]))
                    self.assertIsNot(domains[parameter], cases.CASES[case]["domain"])
                    self.assertIsNot(domains[parameter], cases.request(case, role)["inputs"][parameter])
        for role in ("reference", "original", "accepted", "", None, True):
            with self.subTest(invalid_candidate=role), self.assertRaisesRegex(ValueError, "candidate origin"):
                cases.request("4-A", role)

    def test_task_range_edges_are_distinct_from_the_frozen_finite_domain(self):
        for case, legal, illegal, outside_sample in (
            ("4-A", (1, 2, 3, 4, 60, 61, 96, 97, 98, 99, 100),
             (-1, 0, 101, (1 << 32) - 1), 61),
            ("84-A", (2, 4, 120, 122, 99999994, 99999996, 99999998, 100000000),
             (-2, 0, 1, 3, 99999999, 100000001, 100000002, (1 << 32) - 1), 122),
        ):
            self.assertNotIn(outside_sample, DOMAINS[case])
            for x in legal:
                with self.subTest(case=case, legal=x):
                    self.assertIs(cases.legal_input(case, x), True)
                    for role in ("buggy", "supplied", "reference"):
                        self.assertEqual(cases.value(case, role, x), mathematical_value(case, role, x))
            for x in (*illegal, False, True, 2.0, "2", b"2", None, [], {}):
                with self.subTest(case=case, illegal=x):
                    self.assertIs(cases.legal_input(case, x), False)
                    for role in ("buggy", "supplied", "reference"):
                        with self.assertRaisesRegex(ValueError, "input outside task range"):
                            cases.value(case, role, x)
            with self.assertRaisesRegex(ValueError, "source role"):
                cases.value(case, "accepted", 2)

    def test_finite_request_domain_rejects_empty_unsorted_duplicate_and_ill_typed_axes(self):
        axes = ([], [2, 1], [2, 2], [True], [False], [2.0], ["2"], [-1],
                [1 << 32], list(range(65)), (1, 2))
        for case in DOMAINS:
            parameter = cases.CASES[case]["input"]
            for axis in axes:
                with self.subTest(case=case, axis=axis):
                    request = cases.request(case, "buggy")
                    request["inputs"][parameter] = axis
                    with self.assertRaises(Invalid):
                        validate_request_fields(request)


class CodeflawsOutputCodecTests(unittest.TestCase):
    def test_exact_labels_and_single_decimal_with_surrounding_ascii_whitespace(self):
        samples = {
            "4-A": ((b"YES", 1), (b"NO", 0), (b" \t\r\nYES\v\f", 1), (b"NO\n", 0),
                    (b" " * 125 + b"YES", 1), (b"NO" + b" " * 126, 0)),
            "84-A": ((b"0", 0), (b"3", 3), (b" \t150000000\r\n", 150000000),
                     (b"0003", 3), (b"0" * 128, 0), (b"1" + b" " * 127, 1)),
        }
        for case, pairs in samples.items():
            for raw, expected in pairs:
                with self.subTest(case=case, raw=raw):
                    decoded = cases.decode_output(case, raw)
                    self.assertIs(type(decoded), int)
                    self.assertEqual(decoded, expected)

    def test_empty_mixed_non_ascii_and_malformed_outputs_are_rejected(self):
        common = (b"", b" \t\n", b"\x00", b"\xff", b"1\x00", b"YES NO", b"3 4", b"3\n4")
        malformed = {
            "4-A": (b"yes", b"Yes", b"no", b"1", b"0", b"YES!", b"YES\nNO", b"Y ES"),
            "84-A": (b"YES", b"-1", b"+3", b"3.0", b"3e0", b"0x3", b"1_000", b"1\t0",
                     "\u0663".encode("utf-8"), "\uff13".encode("utf-8"), "\u00a03".encode("utf-8")),
        }
        for case in DOMAINS:
            for raw in (*common, *malformed[case]):
                with self.subTest(case=case, raw=raw), self.assertRaises(ValueError):
                    cases.decode_output(case, raw)

    def test_129_raw_bytes_are_rejected_before_whitespace_or_leading_zero_stripping(self):
        for case, raw in (("4-A", b"YES" + b" " * 126), ("4-A", b"NO" + b" " * 127),
                          ("84-A", b"0" * 129), ("84-A", b"3" + b" " * 128)):
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, "output bound"):
                cases.decode_output(case, raw)


class CodeflawsPointClaimTests(unittest.TestCase):
    def test_refuted_cases_match_compact_checker_on_the_supplied_claim(self):
        for case in DOMAINS:
            request = cases.request(case, "buggy")
            witness = copy.deepcopy(EXPECTED[(case, "buggy")]["witness"])
            before = copy.deepcopy((request, witness))
            counts = Counter()
            compact = compact_check(request, compact_produce(request, witness),
                                    lambda k, n=1: counts.update({k: n}))
            direct = study.point_direct(request, witness)
            with self.subTest(case=case):
                self.assertTrue(exact_equal(study.result_core(direct), EXPECTED[(case, "buggy")]))
                self.assertTrue(exact_equal(study.result_core(compact), study.result_core(direct)))
                self.assertGreater(direct["checked_nodes"], 0)
                self.assertEqual(direct["checked_cells"], direct["checked_nodes"])
                self.assertEqual(compact["checked_cells"], direct["checked_cells"])
                self.assertEqual(dict(counts), {"refutation_cells": direct["checked_cells"]})
                self.assertEqual((request, witness), before)

    def test_valid_nonleast_point_is_checked_without_full_domain_discovery(self):
        request = cases.request("84-A", "buggy")
        witness = {"obligation": "repair", "trace": [], "input": [100000000]}
        self.assertNotEqual(witness, EXPECTED[("84-A", "buggy")]["witness"])
        with patch.object(study, "evaluate_topological", side_effect=AssertionError("full discovery")), \
                patch.object(study, "oracle", side_effect=AssertionError("oracle discovery")), \
                patch.object(study, "produce", side_effect=AssertionError("producer discovery")), \
                patch.object(study, "_evaluate_point", wraps=study._evaluate_point) as evaluate:
            direct = study.point_direct(request, witness)
        evaluate.assert_called_once()
        self.assertEqual(evaluate.call_args.args[2], [100000000])
        self.assertTrue(exact_equal(study.result_core(direct), {"status": "REFUTED", "witness": witness}))
        self.assertEqual(study.result_core(compact_check(request, compact_produce(request, witness))),
                         study.result_core(direct))

    def test_false_obligations_and_incorrect_candidate_traces_are_rejected(self):
        claims = (
            ("4-A", "buggy", "repair", [4], [[0, 1]]),
            ("4-A", "buggy", "defined", [2], [[0, 1]]),
            ("4-A", "buggy", "preserve", [2], [[0, 1]]),
            ("4-A", "buggy", "repair", [2], [[0, 0]]),
            ("4-A", "buggy", "repair", [2], []),
            ("4-A", "buggy", "repair", [2], [[1, 1]]),
            ("4-A", "buggy", "repair", [2], [[0, 1], [0, 1]]),
            ("4-A", "supplied", "repair", [2], [[0, 0]]),
            ("84-A", "buggy", "defined", [2], []),
            ("84-A", "buggy", "preserve", [2], []),
            ("84-A", "buggy", "repair", [2], [[0, 1]]),
            ("84-A", "supplied", "repair", [2], []),
        )
        for case, role, obligation, point, trace in claims:
            with self.subTest(case=case, role=role, obligation=obligation, point=point, trace=trace):
                request = cases.request(case, role)
                witness = {"obligation": obligation, "input": point, "trace": trace}
                with self.assertRaisesRegex(Invalid, "point claim false"):
                    study.point_direct(request, witness)
                with self.assertRaises(Invalid):
                    compact_check(request, compact_produce(request, witness))

    def test_point_membership_is_the_frozen_axis_not_the_whole_task_range(self):
        for case, points in (("4-A", (0, 61, 96, 101)), ("84-A", (0, 3, 122, 100000002))):
            for x in points:
                with self.subTest(case=case, point=x):
                    request = cases.request(case, "buggy")
                    witness = copy.deepcopy(EXPECTED[(case, "buggy")]["witness"])
                    witness["input"] = [x]
                    with self.assertRaisesRegex(Invalid, "point membership"):
                        study.point_direct(request, witness)
                    with self.assertRaisesRegex(Invalid, "outside domain"):
                        compact_check(request, compact_produce(request, witness))

    def test_claim_schema_and_json_integer_types_are_strict(self):
        request = cases.request("4-A", "buggy")
        valid = EXPECTED[("4-A", "buggy")]["witness"]
        invalid = [("schema", obj) for obj in (None, [], (), "claim", {},
                   {**valid, "extra": 0}, {k: v for k, v in valid.items() if k != "trace"})]
        invalid += [("obligation", {**valid, "obligation": value})
                    for value in ("", "accept", None, True, 0, [])]
        invalid += [("input", {**valid, "input": value})
                    for value in (None, {}, (2,), [], [2, 2], [True], [2.0], ["2"])]
        invalid += [("trace", {**valid, "trace": value})
                    for value in (None, {}, (), [(0, 1)], [[0]], [[0, 1, 1]],
                                  [[-1, 1]], [[False, 1]], [[0.0, 1]], [["0", 1]],
                                  [[0, True]], [[0, 1.0]], [[0, "1"]], [[0, 2]], [[0, -1]])]
        for category, witness in invalid:
            with self.subTest(category=category, witness=witness):
                before = copy.deepcopy(witness)
                with self.assertRaisesRegex(Invalid, "point claim schema" if category == "schema" else "point " + category):
                    study.point_direct(request, witness)
                self.assertEqual(witness, before)


class CodeflawsAdmissionAndStudyTests(unittest.TestCase):
    def test_synthetic_original_style_wrappers_are_declined_but_normalizations_are_admitted(self):
        # These fixtures are authored here and only parsed, never compiled/run.
        wrappers = (
            "#include <stdio.h>\nint main(void) { return 0; }\n",
            "int main(void) { return 0; }\n",
            'unsigned f(unsigned w) { printf("YES"); return w; }',
        )
        for source in wrappers:
            with self.subTest(wrapper=source), self.assertRaises(Unsupported):
                Reader(source).program()
        for case, role in EXPECTED:
            request = cases.request(case, role)
            for receiver_role in ROLES:
                with self.subTest(case=case, role=role, source_role=receiver_role):
                    names, _body = Reader(request[receiver_role]).program()
                    self.assertEqual(names, list(request["inputs"]))
                    wrapped = {**request, receiver_role: wrappers[0]}
                    with self.assertRaises(Unsupported):
                        evaluate_topological(wrapped)
            # Admission and repair correctness are different: buggy is REFUTED.
            self.assertEqual(evaluate_topological(request)["status"], EXPECTED[(case, role)]["status"])

    def test_source_identity_metadata_and_receiver_roles_remain_distinct(self):
        metadata = {
            "4-A": ("4-A-bug-18258406-18258457", "4-A-18258406.c", "4-A-18258457.c"),
            "84-A": ("84-A-bug-9385928-9385933", "84-A-9385928.c", "84-A-9385933.c"),
        }
        for case, (subject, buggy_name, supplied_name) in metadata.items():
            sources = cases.CASES[case]["sources"]
            self.assertEqual(cases.CASES[case]["subject"], subject)
            self.assertEqual(set(sources), {"buggy", "supplied"})
            self.assertEqual(sources["buggy"][0], buggy_name)
            self.assertEqual(sources["supplied"][0], supplied_name)
            for _filename, digest in sources.values():
                self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertNotEqual(sources["buggy"][1], sources["supplied"][1])
            request = cases.request(case, "supplied")
            packet = produce(request)
            for role in ROLES:
                with self.subTest(case=case, role=role):
                    self.assertEqual(packet["source_sha256"][role],
                                     hashlib.sha256(request[role].encode("utf-8")).hexdigest())
            # Even equivalent supplied/reference outputs do not make their text interchangeable.
            relabelled = {**request, "candidate": request["reference"]}
            with self.assertRaisesRegex(Invalid, "source binding"):
                check(relabelled, packet)
            swapped = copy.deepcopy(packet)
            swapped["role_roots"]["original"], swapped["role_roots"]["candidate"] = (
                swapped["role_roots"]["candidate"], swapped["role_roots"]["original"])
            with self.assertRaisesRegex(Invalid, "root binding"):
                check(request, rehash(swapped))
            buggy = cases.request(case, "buggy")
            witness = EXPECTED[(case, "buggy")]["witness"]
            compact = compact_produce(buggy, witness)
            changed = {**buggy, "original": cases.function(case, "supplied")}
            with self.assertRaisesRegex(Invalid, "source binding"):
                compact_check(changed, compact)

    def test_serialized_full_and_direct_routes_preserve_all_four_results(self):
        for (case, role), expected in EXPECTED.items():
            for method in ("full", "direct"):
                with self.subTest(case=case, role=role, method=method):
                    result, stages = study.serialize_run(case, role, method)
                    self.assertTrue(exact_equal(study.result_core(result), expected))
                    fields = {"request_construct_ms", "request_encode_ms", "request_decode_ms",
                              "receiver_ms", "result_encode_ms", "total_ms"}
                    if method == "full":
                        fields |= {"producer_ms", "packet_encode_ms", "receiver_request_decode_ms", "packet_decode_ms"}
                    self.assertEqual(set(stages), fields)
                    self.assertTrue(all(type(v) is float and v >= 0 for v in stages.values()))

    def test_offline_replay_records_four_outcomes_without_archive_or_native_work(self):
        reports = {}

        def capture(path, obj):
            reports[path.name] = copy.deepcopy(obj)

        with patch.object(study, "write_json", side_effect=capture), \
                patch.object(study, "write_csv", side_effect=capture), \
                patch.object(study, "inspect", side_effect=AssertionError("archive inspection")), \
                patch.object(study, "run_native", side_effect=AssertionError("native execution")), \
                patch.object(study.tarfile, "open", side_effect=AssertionError("archive read")), \
                patch.object(study.subprocess, "run", side_effect=AssertionError("process execution")):
            outcomes, timings = study.replay_models(Path("unused-model-report"), 1)
        self.assertEqual(set(reports), {"requests.json", "model-outcomes.json", "timing.csv"})
        self.assertEqual(reports["requests.json"], [cases.request(case, role) for case, role in EXPECTED])
        self.assertEqual(reports["model-outcomes.json"], outcomes)
        self.assertEqual(reports["timing.csv"], timings)
        self.assertEqual(len(outcomes), 4)
        self.assertEqual(len(timings), 8)
        for row in outcomes:
            key = row["case"], row["candidate_origin"]
            with self.subTest(case=key):
                self.assertEqual(study.result_core(row), EXPECTED[key])
                self.assertEqual(row["points"], 64)
                self.assertEqual(row["full_cells"], row["direct_cells"])
                self.assertEqual(row["full_cells"], row["nodes"] * 64)
                self.assertGreater(row["full_bytes"], 0)
                if row["status"] == "ACCEPT":
                    self.assertIsNone(row["compact"])
                else:
                    self.assertEqual(row["compact"]["status"], "REFUTED")
                    self.assertEqual(row["compact"]["cells"], row["nodes"])
                    self.assertGreater(row["compact"]["canonical_bytes"], 0)
        for case, role in EXPECTED:
            paired = [r for r in timings if (r["case"], r["candidate_origin"]) == (case, role)]
            self.assertEqual([(r["method"], r["rank"], r["repetition"]) for r in paired],
                             [("full", 0, 0), ("direct", 1, 0)])


class CodeflawsTimingTests(unittest.TestCase):
    def test_construction_and_request_encoding_costs_are_inside_both_totals(self):
        real_request, real_dumps = study.request, json.dumps
        for method in ("full", "direct"):
            now, events = [0], []

            def construct(case, role):
                events.append("construct")
                now[0] += 5_000_000
                return real_request(case, role)

            def encode(obj, *args, **kwargs):
                if type(obj) is dict and {"original", "candidate", "reference"} <= set(obj):
                    events.append("request_encode")
                    now[0] += 7_000_000
                return real_dumps(obj, *args, **kwargs)

            with self.subTest(method=method), \
                    patch.object(study, "request", side_effect=construct), \
                    patch.object(study.json, "dumps", side_effect=encode), \
                    patch.object(study.time, "perf_counter_ns", side_effect=lambda: now[0]):
                result, stages = study.serialize_run("4-A", "buggy", method)
            self.assertEqual(study.result_core(result), EXPECTED[("4-A", "buggy")])
            self.assertEqual(events, ["construct", "request_encode"])
            self.assertEqual(stages["request_construct_ms"], 5.0)
            self.assertEqual(stages["request_encode_ms"], 7.0)
            self.assertEqual(stages["total_ms"], 12.0)
            self.assertEqual(sum(v for k, v in stages.items() if k != "total_ms"), 12.0)

    def test_two_matching_api_and_serialized_warmups_precede_alternating_measurements(self):
        real_serial, real_full, real_direct = study.serialize_run, study.check, study.evaluate_topological
        events, in_serial = [], [False]

        def api_key(request):
            return request["id"][len("codeflaws-"):].rsplit("-", 1)

        def full(request, packet, count=None, **kwargs):
            if not in_serial[0] and count is None:
                events.append(("api", *api_key(request), "full"))
            if in_serial[0]:
                self.assertIsNone(count)
            return real_full(request, packet, count, **kwargs)

        def direct(request, count=None):
            if not in_serial[0] and count is None:
                events.append(("api", *api_key(request), "direct"))
            if in_serial[0]:
                self.assertIsNone(count)
            return real_direct(request, count)

        def serialized(case, role, method):
            events.append(("serialized", case, role, method))
            in_serial[0] = True
            try:
                return real_serial(case, role, method)
            finally:
                in_serial[0] = False

        with patch.object(study, "serialize_run", side_effect=serialized), \
                patch.object(study, "check", side_effect=full), \
                patch.object(study, "evaluate_topological", side_effect=direct), \
                patch.object(study, "write_json"), patch.object(study, "write_csv"):
            outcomes, timings = study.replay_models(Path("unused-timing-report"), 2)
        for case, role in EXPECTED:
            actual = [(kind, method) for kind, c, r, method in events if (c, r) == (case, role)]
            # Two warmups and two repetitions, each exercising both exact workflows.
            expected = [(kind, method) for _phase in range(2)
                        for order in (("full", "direct"), ("direct", "full"))
                        for method in order for kind in ("api", "serialized")]
            self.assertEqual(actual, expected)
            rows = [r for r in timings if (r["case"], r["candidate_origin"]) == (case, role)]
            self.assertEqual([(r["repetition"], r["rank"], r["method"]) for r in rows],
                             [(0, 0, "full"), (0, 1, "direct"), (1, 0, "direct"), (1, 1, "full")])
            for row in rows:
                self.assertGreaterEqual(row["request_construct_ms"], 0)
                self.assertGreaterEqual(row["request_encode_ms"], 0)
        self.assertEqual(len(events), 64)
        self.assertEqual(len(timings), 16)
        for row in outcomes:
            count = row["operation_counts"]
            self.assertEqual(count["full"], {"proof_cells": row["full_cells"]})
            self.assertEqual(count["direct"], {"topological_cells": row["direct_cells"]})
            if row["compact"] is not None:
                self.assertEqual(row["compact"]["operation_counts"]["compact"],
                                 {"refutation_cells": row["nodes"]})
                self.assertEqual(row["compact"]["operation_counts"]["point_direct"],
                                 {"refutation_cells": row["nodes"]})


class CodeflawsDriverPathTests(unittest.TestCase):
    def test_cli_resolves_relative_paths_before_native_dispatch(self):
        reports = {}
        with ExitStack() as stack:
            base = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="p004-owned-paths-")))
            original_cwd = Path.cwd()
            os.chdir(base)
            stack.callback(os.chdir, original_cwd)
            # Inert owned markers satisfy path checks; neither is ever opened as an archive/program.
            compiler = Path("toolchain") / "owned-compiler"
            compiler.parent.mkdir()
            compiler.write_bytes(b"inert owned compiler marker")
            archive = Path("owned-archive-marker")
            archive.write_bytes(b"inert owned archive marker")
            output = Path("relative-output")
            rows = [{"status": "ACCEPT", "full_cells": 1, "direct_cells": 1} for _ in range(4)]
            stack.enter_context(patch.object(sys, "argv", ["codeflaws_source_study.py", "--output", str(output),
                                                          "--archive", str(archive), "--compiler", str(compiler),
                                                          "--execute-reviewed", "--repetitions", "1"]))
            stack.enter_context(patch.object(sys, "stdout", io.StringIO()))
            stack.enter_context(patch.object(study, "fingerprint", return_value="a" * 64))
            stack.enter_context(patch.object(study, "pin_affinity"))
            # platform.platform()/processor() can invoke uname through subprocess
            # on Linux. This path-dispatch unit uses owned metadata as well as
            # owned process/archive doubles; production metadata remains real.
            platform_query = stack.enter_context(patch.object(study.platform, "platform", return_value="owned-platform"))
            stack.enter_context(patch.object(study.platform, "machine", return_value="owned-machine"))
            stack.enter_context(patch.object(study.platform, "processor", return_value="owned-processor"))
            replay = stack.enter_context(patch.object(study, "replay_models", return_value=(rows, [])))
            inspect = stack.enter_context(patch.object(study, "inspect", return_value=({}, {})))
            native = stack.enter_context(patch.object(study, "run_native", return_value={"owned_fixture": True}))
            stack.enter_context(patch.object(study, "write_json",
                                            side_effect=lambda p, obj: reports.update({p.name: copy.deepcopy(obj)})))
            stack.enter_context(patch.object(study.tarfile, "open", side_effect=AssertionError("actual archive open")))
            stack.enter_context(patch.object(study.subprocess, "run", side_effect=AssertionError("actual process")))
            study.main()
            self.assertEqual(replay.call_args.args[0], (base / output).resolve())
            self.assertEqual(inspect.call_args.args[:2], ((base / archive).resolve(), (base / output).resolve()))
            self.assertEqual(native.call_args.args[0], (base / archive).resolve())
            self.assertEqual(native.call_args.args[1], (base / output).resolve())
            self.assertEqual(native.call_args.args[4], (base / compiler).resolve())
            self.assertEqual(reports["summary.json"]["native"], {"owned_fixture": True})
            platform_query.assert_called_once_with()
            self.assertEqual(reports["summary.json"]["environment"]["platform"], "owned-platform")
            self.assertEqual(reports["summary.json"]["environment"]["machine"], "owned-machine")
            self.assertEqual(reports["summary.json"]["environment"]["processor_identifier"], "owned-processor")


class CodeflawsNativeDriverTests(unittest.TestCase):
    """Exercise persistence with owned files and mocked processes/tar streams."""

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.base = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="p004-owned-native-")))
        self.output = self.base / "output"
        self.output.mkdir()
        self.compiler = self.base / "owned-compiler"
        self.compiler.write_bytes(b"inert owned compiler marker")
        self.archive = self.base / "owned-archive-marker"
        self.archive.write_bytes(b"inert owned archive marker")
        self.fixture_cases = copy.deepcopy(cases.CASES)
        self.chosen = {}
        for case, info in self.fixture_cases.items():
            info["domain"] = [2, 4]
            for role in ("buggy", "supplied"):
                source = ("/* owned " + case + " " + role + " fixture; never compiled */\n").encode("ascii")
                self.chosen[(case, role)] = source
                filename, _digest = info["sources"][role]
                info["sources"][role] = (filename, hashlib.sha256(source).hexdigest())
        self.selection = {case: {"repair": [], "heldout": []} for case in self.fixture_cases}
        self.tar = OwnedTar([])
        self.processes = OwnedProcesses()
        self.stack.enter_context(patch.object(study, "CASES", self.fixture_cases))
        self.stack.enter_context(patch.object(study, "ARCHIVE_BYTES", self.archive.stat().st_size))
        self.stack.enter_context(patch.object(study, "fingerprint", return_value=study.ARCHIVE_SHA))
        self.stack.enter_context(patch.object(study.tarfile, "open", side_effect=lambda *_a, **_k: self.tar))
        self.stack.enter_context(patch.object(study.subprocess, "run", side_effect=AssertionError("actual process")))
        self.stack.enter_context(patch.object(study.subprocess, "Popen",
                                            side_effect=lambda *a, **k: self.processes.popen(*a, **k)))

    def run_owned(self, *, zig=False):
        return study.run_native(self.archive, self.output, self.chosen, self.selection, self.compiler, zig)

    def json_record(self, filename):
        return json.loads((self.output / filename).read_text(encoding="utf-8"))

    def persisted_objects(self):
        def walk(obj):
            if isinstance(obj, dict):
                yield obj
                for value in obj.values():
                    yield from walk(value)
            elif isinstance(obj, list):
                for value in obj:
                    yield from walk(value)

        return [obj for path in self.output.rglob("*.json")
                for obj in walk(json.loads(path.read_text(encoding="utf-8")))]

    def assert_raw_retained(self, *streams):
        payloads = [path.read_bytes() for path in self.output.rglob("*") if path.is_file()]
        for stream in streams:
            self.assertIn(stream, payloads)

    def install_selected_fixture(self):
        prefix = "codeflaws/" + self.fixture_cases["4-A"]["subject"] + "/"
        slots = [prefix + "input" + str(index).zfill(2) for index in range(1, 10)]
        self.selection["4-A"]["repair"] = slots[:8]
        entries = [
            (slots[0], b"2\n", None, True), (prefix + "output01", b"NO\n", None, True),
            (slots[1], b"4\n", None, True),  # Missing output, never replaced by slot09.
            (slots[2], b"0\n", None, True), (prefix + "output03", b"NO\n", None, True),
            (slots[3], b"2\n", 70000, True), (prefix + "output04", b"NO\n", None, True),
            (slots[4], b"4\n", None, False), (prefix + "output05", b"YES\n", None, True),
            (slots[5], b"4\n", None, True), (prefix + "output06", b"MAYBE\n", None, True),
            (slots[6], b"2 4\n", None, True), (prefix + "output07", b"NO\n", None, True),
            (slots[7], b"4\n", None, True), (prefix + "output08", b"YES\n", None, True),
            (slots[8], b"6\n", None, True), (prefix + "output09", b"YES\n", None, True),
        ]
        self.tar = OwnedTar(entries)
        return slots

    def test_metadata_selection_keeps_oversized_nonregular_slots_without_reading_payloads(self):
        slots = self.install_selected_fixture()
        entries = [(member.name, self.tar.payloads[id(member)], member.size, member.isfile())
                   for member in self.tar.members]
        subjects = [info["subject"] for info in self.fixture_cases.values()]
        for case, info in self.fixture_cases.items():
            for role, (filename, _digest) in info["sources"].items():
                entries.append(("codeflaws/" + info["subject"] + "/" + filename,
                                self.chosen[(case, role)], None, True))
        for index in range(298):
            subject = "owned-subject-" + str(index)
            subjects.append(subject)
            for version in (1, 2):
                entries.append((f"codeflaws/{subject}/{1000 + index}-A-{version}.c",
                                b"unsigned f(unsigned x) { return x; }", None, True))
        # Reverse metadata order to require lexical freezing rather than stream-order selection.
        self.tar = OwnedTar(list(reversed(entries)))
        reports = {}
        with patch.object(study, "ARCHIVE_BYTES", self.archive.stat().st_size), \
                patch.object(study, "fingerprint", return_value=study.ARCHIVE_SHA), \
                patch.object(Path, "read_text", return_value="\n".join(subjects)), \
                patch.object(study, "write_json",
                             side_effect=lambda p, obj: reports.update({p.name: copy.deepcopy(obj)})):
            chosen, selection = study.inspect(self.archive, self.output)
        self.assertEqual(set(chosen), set(self.chosen))
        self.assertEqual(selection["4-A"]["repair"], slots[:8])
        self.assertNotIn(slots[8], selection["4-A"]["repair"])
        self.assertEqual(reports["test-selection.json"], selection)
        self.assertEqual(len(self.tar.reads), 600)
        self.assertTrue(all(name.endswith(".c") for name in self.tar.reads))

    def test_selected_missing_invalid_slots_are_accounted_without_replacement(self):
        slots = self.install_selected_fixture()
        before = copy.deepcopy(self.selection)
        rows, valid = study.read_selected_tests(self.archive, self.selection)
        selected = [row for row in rows if row["test_member"] is not None]
        self.assertEqual([row["test_member"] for row in selected], slots[:8])
        self.assertEqual([row["slot"] for row in selected], list(range(1, 9)))
        self.assertEqual([row["selection_status"] for row in selected],
                         ["valid", "unavailable", "invalid", "invalid", "invalid", "invalid", "invalid", "valid"])
        self.assertTrue(all(row["reason"] for row in selected if row["selection_status"] != "valid"))
        self.assertEqual([(row["test_member"], raw, target) for row, raw, target in valid],
                         [(slots[0], b"2\n", 0), (slots[7], b"4\n", 1)])
        empty_splits = [row for row in rows if row["test_member"] is None]
        self.assertEqual(len(empty_splits), 3)
        self.assertTrue(all(row["slot"] is None and row["selection_status"] == "unavailable"
                            for row in empty_splits))
        self.assertNotIn(slots[3], self.tar.reads)
        self.assertNotIn(slots[4], self.tar.reads)
        self.assertNotIn(slots[8], self.tar.reads)
        self.assertNotIn(study.test_output_member(slots[8]), self.tar.reads)
        self.assertEqual(self.selection, before)
        self.assertEqual(self.processes.calls, [])

    def test_selected_pair_accounting_is_persisted_and_only_valid_pairs_execute(self):
        slots = self.install_selected_fixture()
        summary = self.run_owned()
        self.assertEqual(summary["compiled_translation_units"], 4)
        self.assertEqual(summary["domain_process_executions"], 8)
        self.assertEqual(summary["domain_observation_agreement"], 8)
        self.assertEqual(summary["existing_test_execution_attempts"], 4)
        self.assertEqual(summary["existing_test_executions"], 4)
        selected = [row for row in self.json_record("existing-test-selection-status.json")
                    if row["test_member"] is not None]
        self.assertEqual([row["test_member"] for row in selected], slots[:8])
        for row in summary["existing_test_outcomes"]:
            if row["case"] == "4-A" and row["split"] == "repair":
                self.assertEqual({key: row[key] for key in ("selected", "valid", "invalid", "unavailable", "total")},
                                 {"selected": 8, "valid": 2, "invalid": 5, "unavailable": 1, "total": 2})
                self.assertIs(row["split_available"], True)
                self.assertEqual(row["execution_errors"], 0)
                self.assertEqual(row["matched_expected"], 1 if row["role"] == "buggy" else 2)
            else:
                self.assertIs(row["split_available"], False)
                self.assertTrue(all(row[key] == 0 for key in ("selected", "valid", "invalid", "unavailable", "total")))
        with (self.output / "existing-test-observations.csv").open(encoding="utf-8", newline="") as stream:
            observed = list(csv.DictReader(stream))
        self.assertEqual(len(observed), 4)
        self.assertEqual({row["test_member"] for row in observed}, {slots[0], slots[7]})
        self.assertTrue(all(row["native_observed"] in {"0", "1"} and row["returncode"] == "0" for row in observed))
        self.assertEqual(sum(call["stage"] == "execute" for call in self.processes.calls), 12)
        self.assertNotIn(slots[8], self.tar.reads)

    def test_native_relative_paths_remain_absolute_under_isolated_cwd_for_both_frontends(self):
        original_cwd = Path.cwd()
        os.chdir(self.base)
        self.stack.callback(os.chdir, original_cwd)
        for zig in (False, True):
            with self.subTest(zig=zig):
                self.output = self.base / ("relative-output-" + str(int(zig)))
                self.output.mkdir()
                self.processes = OwnedProcesses()
                study.run_native(Path(self.archive.name), Path(self.output.name), self.chosen,
                                 self.selection, Path(self.compiler.name), zig)
                for call in self.processes.calls:
                    command = call["command"]
                    self.assertEqual(Path(command[0]), self.compiler.resolve() if call["stage"] != "execute"
                                     else self.output.resolve() / "private-native" / Path(command[0]).name)
                    self.assertTrue(Path(command[0]).is_absolute())
                    if call["cwd"] is not None:
                        self.assertEqual(Path(call["cwd"]), self.output.resolve() / "private-native")
                    for cache in call["caches"].values():
                        self.assertTrue(Path(cache).is_absolute())
                        self.assertTrue(Path(cache).is_relative_to(self.output.resolve() / "private-native"))
                    if call["stage"] == "compile":
                        output_index = command.index("-o")
                        self.assertTrue(Path(command[output_index - 1]).is_absolute())
                        self.assertTrue(Path(command[output_index + 1]).is_absolute())
                    if call["stage"] != "execute":
                        self.assertEqual(command[1:2] == ["cc"], zig)

    def test_compile_failure_persists_actual_returncode_and_both_raw_streams(self):
        stdout, stderr = b"owned failing compile stdout\n", b"owned failing compile stderr\n"

        def fail(stage, record, _index):
            if stage == "compile":
                return study.subprocess.CompletedProcess(record["command"], 7,
                    stdout.decode("ascii") if record["text"] else stdout,
                    stderr.decode("ascii") if record["text"] else stderr)

        self.processes.fail = fail
        with self.assertRaises(RuntimeError):
            self.run_owned()
        self.assert_raw_retained(stdout, stderr)
        objects = self.persisted_objects()
        self.assertTrue(any(obj.get("returncode") == 7 for obj in objects))
        self.assertTrue(any(obj.get("returncode") == 0 for obj in objects))
        self.assertFalse(any(call["stage"] == "execute" for call in self.processes.calls))

    def test_domain_timeout_persists_partial_raw_streams_and_earlier_observations(self):
        stdout, stderr = b"owned partial timeout stdout", b"owned timeout stderr"
        executed = 0

        def fail(stage, record, _index):
            nonlocal executed
            if stage == "execute":
                executed += 1
                if executed == 2:
                    return study.subprocess.TimeoutExpired(record["command"], record["timeout"],
                                                           output=stdout, stderr=stderr)

        self.processes.fail = fail
        with self.assertRaises(RuntimeError):
            self.run_owned()
        self.assert_raw_retained(stdout, stderr)
        with (self.output / "native-observations.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertTrue(any(row["input"] == "2" and row["native_observed"] == "1" for row in rows))
        self.assertTrue(any(row["input"] == "4" and row["agrees"] == "False" for row in rows))
        self.assertTrue(any("timeout" in str(obj.get("outcome", "")).lower()
                            or "TimeoutExpired" in str(obj.get("error", "")) for obj in self.persisted_objects()))

    def test_domain_decode_failure_retains_raw_zero_exit_and_failure_row(self):
        stdout, stderr = b"owned invalid label\n", b"owned execution diagnostic\n"
        executed = 0

        def fail(stage, record, _index):
            nonlocal executed
            if stage == "execute":
                executed += 1
                if executed == 2:
                    return study.subprocess.CompletedProcess(record["command"], 0, stdout, stderr)

        self.processes.fail = fail
        with self.assertRaises((RuntimeError, ValueError)):
            self.run_owned()
        self.assert_raw_retained(stdout, stderr)
        with (self.output / "native-observations.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertTrue(any(row["input"] == "2" and row["agrees"] == "True" for row in rows))
        self.assertTrue(any(row["input"] == "4" and row["returncode"] == "0"
                            and row["agrees"] == "False" for row in rows))
        self.assertTrue(any("decode" in str(obj).lower() for obj in self.persisted_objects()))

    def test_failed_diagnostics_persist_returncodes_and_raw_records_before_any_compile(self):
        for failed_stage in ("version", "macros"):
            with self.subTest(stage=failed_stage):
                self.output = self.base / ("failed-" + failed_stage)
                self.output.mkdir()
                self.processes = OwnedProcesses()
                stdout = ("owned " + failed_stage + " stdout\n").encode("ascii")
                stderr = ("owned " + failed_stage + " stderr\n").encode("ascii")

                def fail(stage, record, _index):
                    if stage == failed_stage:
                        return study.subprocess.CompletedProcess(record["command"], 13, stdout, stderr)

                self.processes.fail = fail
                with self.assertRaisesRegex(RuntimeError, "compiler .* query failed"):
                    self.run_owned()
                self.assert_raw_retained(stdout, stderr)
                record = self.json_record("compile-record.json")
                self.assertEqual(record["compiles"], [])
                self.assertEqual(record["diagnostics"][-1]["returncode"], 13)
                self.assertEqual(record["diagnostics"][-1]["outcome"], "nonzero")
                self.assertFalse(any(call["stage"] == "compile" for call in self.processes.calls))

    def test_spawn_failure_is_retained_with_no_fabricated_returncode(self):
        with patch.object(study.subprocess, "Popen", side_effect=OSError("owned spawn failure")):
            with self.assertRaisesRegex(RuntimeError, "version query failed"):
                self.run_owned()
        records = self.json_record("private-native/subprocess-records.json")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], "spawn_error")
        self.assertIsNone(records[0]["returncode"])
        self.assertIn("owned spawn failure", records[0]["error"])
        self.assertEqual((self.output / records[0]["stdout_path"]).read_bytes(), b"")
        self.assertEqual((self.output / records[0]["stderr_path"]).read_bytes(), b"")
        self.assertEqual(self.json_record("compile-record.json")["diagnostics"][0], records[0])

    def test_observation_overflow_retains_bounded_raw_prefix_and_explicit_failure(self):
        def fail(stage, record, _index):
            if stage == "execute":
                return study.subprocess.CompletedProcess(record["command"], 0, b"A" * 129, b"owned overflow stderr")

        self.processes.fail = fail
        with self.assertRaisesRegex(RuntimeError, "native/model observation disagreement"):
            self.run_owned()
        failed = self.json_record("private-native/subprocess-records.json")[-1]
        self.assertEqual(failed["outcome"], "output_limit")
        self.assertEqual(failed["stdout_bytes_seen"], 129)
        self.assertEqual(failed["stdout_limit"], 128)
        self.assertIs(failed["stdout_truncated"], True)
        self.assertEqual((self.output / failed["stdout_path"]).read_bytes(), b"A" * 128)
        self.assert_raw_retained(b"owned overflow stderr")

    def test_existing_test_timeout_is_counted_and_raw_failure_is_retained(self):
        self.install_selected_fixture()
        executed = 0

        def fail(stage, record, _index):
            nonlocal executed
            if stage == "execute":
                executed += 1
                if executed == 9:  # Eight successful domain observations precede existing tests.
                    return study.subprocess.TimeoutExpired(record["command"], 5,
                                                           output=b"owned existing partial", stderr=b"owned existing timeout")

        self.processes.fail = fail
        summary = self.run_owned()
        self.assertEqual(summary["existing_test_execution_attempts"], 4)
        buggy = next(row for row in summary["existing_test_outcomes"]
                     if (row["case"], row["role"], row["split"]) == ("4-A", "buggy", "repair"))
        self.assertEqual(buggy["execution_errors"], 1)
        self.assertEqual(buggy["matched_expected"], 1)
        self.assertEqual(buggy["total"], 2)
        self.assert_raw_retained(b"owned existing partial", b"owned existing timeout")
        with (self.output / "existing-test-observations.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["outcome"], "timeout")
        self.assertEqual(rows[0]["native_observed"], "")
        self.assertEqual(rows[0]["matches_existing_expected"], "False")


if __name__ == "__main__":
    unittest.main(verbosity=2)
