"""Owned finite repair/trace regressions; no native or third-party execution.

The literal oracle fixes source-preorder sites independently of the AST
interpreter and both production frontends. The arithmetic example repairs
unsigned increment at UINT_MAX, with overfit/preservation/definedness controls.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
from checker import Session
from holdout_differential import (
    MASK, Decl, SetVar, If, Return, execute, render_program, oracle,
    u_const, u_var, u_bin, b_rel, b_bin,
)
from proof_dag_checker import Invalid, check, evaluate_topological
from proof_dag_producer import produce
from refutation_witness_checker import check as compact_check
from refutation_witness_producer import produce as compact_produce

AXIS = [0, 1, 3, 31, 32, 2147483647, 2147483648, 4294967295]
VARIANTS = ("unrepaired", "correct", "overfit", "regression", "defined")
RECORDS = []


def repair_case(variant):
    # Both branches contain a site; the later site is 3 even after a skip.
    prefix = (
        Decl("r", u_bin("+", u_var("x"), u_const(1))),
        Decl("scratch", u_const(0)),
        If(b_rel("==", u_var("x"), u_const(0)),
           (If(b_rel("==", u_var("y"), u_const(0)),
               (SetVar("scratch", u_const(1)),),
               (SetVar("scratch", u_const(2)),)),),
           (If(b_rel("==", u_var("y"), u_const(1)),
               (SetVar("scratch", u_const(3)),),
               (SetVar("scratch", u_const(4)),)),)),
    )
    at_max = b_rel("==", u_var("x"), u_const(MASK))
    original = prefix + (If(at_max, (SetVar("r", u_var("r")),),
                           (SetVar("r", u_var("r")),)), Return(u_var("r")))
    condition = at_max
    if variant == "overfit":
        condition = b_bin("&&", at_max, b_rel("==", u_var("y"), u_const(0)))
    elif variant == "regression":
        condition = b_rel(">=", u_var("x"), u_const(2147483648))
    if variant == "unrepaired":
        candidate = original
    else:
        candidate = prefix + (If(condition, (SetVar("r", u_const(MASK)),),
                                (SetVar("r", u_var("r")),)), Return(u_var("r")))
    if variant == "defined":
        # This is interpreted as data only; no undefined native C is run.
        candidate = (Decl("poison", u_bin("/", u_const(1),
                            u_bin("^", u_var("x"), u_const(MASK)))),) + candidate
    reference = (
        Decl("r", u_var("x")),
        If(at_max, (SetVar("r", u_const(MASK)),),
           (SetVar("r", u_bin("+", u_var("x"), u_const(1))),)),
        Return(u_var("r")),
    )
    request = {
        "id": "owned-nested-saturating-" + variant,
        "word_bits": 32, "inputs": {"x": AXIS[:], "y": AXIS[:]},
        "original": render_program(("x", "y"), original),
        "candidate": render_program(("x", "y"), candidate),
        "reference": render_program(("x", "y"), reference),
        "repair_guard": "x == 4294967295u",
    }
    return request, original, candidate, reference


def literal_observation(variant, x, y):
    if variant == "defined" and x == MASK:
        return False, None, []
    value = (x + 1) % (2 ** 32)
    condition = x == MASK
    if variant == "overfit": condition = x == MASK and y == 0
    if variant == "regression": condition = x >= 2147483648
    if variant != "unrepaired" and condition: value = MASK
    trace = [[0, int(x == 0)],
             [1, int(y == 0)] if x == 0 else [2, int(y == 1)],
             [3, int(condition)]]
    return True, value, trace


def literal_result(variant):
    bad = [[], [], []]
    for x, y in itertools.product(AXIS, AXIS):
        defined, value, trace = literal_observation(variant, x, y)
        selected = x == MASK
        truth = (defined,
                 not selected or (defined and value == min(x + 1, MASK)),
                 selected or (defined and value == (x + 1) % (2 ** 32)))
        for index, ok in enumerate(truth):
            if not ok: bad[index].append((trace, [x, y]))
    for name, rows in zip(("defined", "repair", "preserve"), bad):
        if rows:
            trace, point = min(rows)
            return {"status": "REFUTED", "witness": {
                "obligation": name, "trace": trace, "input": point}}
    return {"status": "ACCEPT", "witness": None}


class NestedTraceRepairTests(unittest.TestCase):
    def test_skipped_source_sites_are_not_runtime_ordinals(self):
        req, original, candidate, reference = repair_case("unrepaired")
        expected = (True, 2, [[0, 0], [2, 1], [3, 0]])
        self.assertEqual(execute(candidate, {"x": 1, "y": 1}), expected)
        self.assertEqual(Session(req).run("candidate", {"x": 1, "y": 1}),
                         (True, 2, ((0, 0), (2, 1), (3, 0))))

    def test_reused_ast_object_has_distinct_source_occurrences(self):
        shared = If(b_rel("==", u_var("y"), u_const(0)),
                    (SetVar("r", u_const(1)),), (SetVar("r", u_const(2)),))
        body = (Decl("r", u_const(0)),
                If(b_rel("==", u_var("x"), u_const(0)), (shared,), (shared,)),
                shared, Return(u_var("r")))
        self.assertEqual(execute(body, {"x": 1, "y": 0}),
                         (True, 1, [[0, 0], [2, 1], [3, 1]]))

    def test_undefined_guard_emits_no_decision_or_later_event(self):
        req, _p, body, _t = repair_case("correct")
        guard = b_rel("==", u_bin("/", u_const(1), u_var("y")), u_const(0))
        broken = body[:-2] + (If(guard, (), ()),) + body[-2:]
        self.assertEqual(execute(broken, {"x": 1, "y": 0}),
                         (False, None, [[0, 0], [2, 0]]))
        source = render_program(("x", "y"), broken)
        altered = dict(req, id="owned-nested-undefined-guard", candidate=source)
        self.assertEqual(Session(altered).run("candidate", {"x": 1, "y": 0}),
                         (False, None, ((0, 0), (2, 0))))

    def test_actual_owned_repair_and_regressions(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                req, original, candidate, reference = repair_case(variant)
                session = Session(req)
                observations = []
                for x, y in itertools.product(AXIS, AXIS):
                    expected = literal_observation(variant, x, y)
                    ast_result = execute(candidate, {"x": x, "y": y})
                    self.assertEqual(ast_result, expected)
                    result = session.run("candidate", {"x": x, "y": y})
                    self.assertEqual((result[0], result[1], [list(e) for e in result[2]]), expected)
                    observations.append({"input": [x, y], "literal": expected,
                                         "ast": ast_result,
                                         "concrete": [result[0], result[1],
                                                      [list(e) for e in result[2]]]})
                expected_result = literal_result(variant)
                self.assertEqual(oracle(req, original, candidate, reference), expected_result)
                cert = produce(req)
                full = check(req, cert)
                direct = evaluate_topological(req)
                for result in (full, direct):
                    self.assertEqual({k: result[k] for k in ("status", "witness")}, expected_result)
                self.assertEqual(full["checked_cells"], direct["checked_cells"])
                if full["status"] == "REFUTED":
                    packet = compact_produce(req, full["witness"])
                    compact = compact_check(req, packet)
                    self.assertEqual(compact["witness"], full["witness"])
                    compact_result = {k: compact[k] for k in ("status", "witness", "checked_cells")}
                else:
                    fake = compact_produce(req, {"obligation": "repair", "input": [MASK, 0],
                                               "trace": literal_observation(variant, MASK, 0)[2]})
                    with self.assertRaisesRegex(Invalid, "claimed obligation is true"):
                        compact_check(req, fake)
                    compact_result = {"status": "INVALID", "control": "claimed obligation is true"}
                RECORDS.append({"variant": variant, "request": req,
                                "point_observations": len(AXIS) ** 2,
                                "result": expected_result, "checked_cells": full["checked_cells"],
                                "full": {k: full[k] for k in ("status", "witness", "checked_cells")},
                                "direct": {k: direct[k] for k in ("status", "witness", "checked_cells")},
                                "compact": compact_result, "observations": observations})

    def test_compact_rejects_runtime_renumbered_trace(self):
        req, _p, _q, _t = repair_case("unrepaired")
        witness = literal_result("unrepaired")["witness"]
        self.assertEqual(witness, {"obligation": "repair", "input": [MASK, 0],
                                   "trace": [[0, 0], [2, 0], [3, 1]]})
        authentic = compact_produce(req, witness)
        self.assertEqual(compact_check(req, authentic)["witness"], witness)
        wrong = copy.deepcopy(witness)
        wrong["trace"] = [[index, bit] for index, (_site, bit) in enumerate(wrong["trace"])]
        with self.assertRaisesRegex(Invalid, "refutation trace mismatch"):
            compact_check(req, compact_produce(req, wrong))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.report is not None and args.report.exists():
        parser.error("report must not already exist")
    result = unittest.TestResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(NestedTraceRepairTests).run(result)
    report = {"schema": "owned-nested-trace-repair-v2",
              "outcome": "PASS" if result.wasSuccessful() else "FAIL",
              "tests_run": result.testsRun,
              "failures": [[str(test), detail] for test, detail in result.failures],
              "errors": [[str(test), detail] for test, detail in result.errors],
              "test_names": unittest.defaultTestLoader.getTestCaseNames(NestedTraceRepairTests),
              "request_count": len(RECORDS),
              "point_observations": sum(row["point_observations"] for row in RECORDS),
              "cases": RECORDS, "native_execution": False, "third_party_code_execution": False,
              "scope": "Owned 64-point unsigned saturation requests and nested source-site semantics; not a public repair benchmark."}
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__": raise SystemExit(main())
