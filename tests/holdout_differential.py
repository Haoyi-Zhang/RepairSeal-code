#!/usr/bin/env python3
"""Independent grammar-based differential campaign for the proof checker.

The generator and oracle in this file do not import either frontend's parser,
compiler, or evaluator.  They construct a small AST directly, render it to the
admitted C fragment, and interpret it with a separately written statement and
expression semantics.  The campaign was added after the designed fixtures and
structured stress template were frozen, so it serves as a post hoc template-overfitting
check rather than as preregistered or public-benchmark evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import resource
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]
from proof_dag_checker import Invalid, Unsupported, check as proof_check, evaluate_topological
from proof_dag_producer import produce
from refutation_witness_checker import check as refutation_check
from refutation_witness_producer import produce as produce_refutation

MASK = (1 << 32) - 1
NAMES = ("x", "y", "z", "t")
VARIANTS = ("accept", "repair", "preserve", "defined")
CAMPAIGN_SEED = 0x51A7C0DE


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def save(path: Path, value: Any, *, sort_keys: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=sort_keys) + "\n")


def save_request(path: Path, request: dict[str, Any]) -> None:
    """Persist the generator-declared coordinate order verbatim."""
    save(path, request, sort_keys=False)


# Expression tuples: (tag, ...).  Sort is implicit by constructor family.
def u_const(value: int): return ("u", value & MASK)
def u_var(name: str): return ("var", name)
def u_unary(arg): return ("~", arg)
def u_bin(op: str, left, right): return (op, left, right)
def b_not(arg): return ("!", arg)
def b_bin(op: str, left, right): return (op, left, right)
def b_rel(op: str, left, right): return (op, left, right)


def render_u(expr) -> str:
    op = expr[0]
    if op == "u": return f"{expr[1]}u"
    if op == "var": return expr[1]
    if op == "~": return f"(~{render_u(expr[1])})"
    return f"({render_u(expr[1])} {op} {render_u(expr[2])})"


def render_b(expr) -> str:
    op = expr[0]
    if op == "!": return f"(!{render_b(expr[1])})"
    if op in {"&&", "||"}: return f"({render_b(expr[1])} {op} {render_b(expr[2])})"
    return f"({render_u(expr[1])} {op} {render_u(expr[2])})"


def eval_u(expr, env: dict[str, int]) -> tuple[bool, int]:
    op = expr[0]
    if op == "u": return True, expr[1]
    if op == "var": return True, env[expr[1]]
    if op == "~":
        defined, value = eval_u(expr[1], env)
        return defined, (~value) & MASK
    dl, left = eval_u(expr[1], env)
    dr, right = eval_u(expr[2], env)
    defined = dl and dr
    if op == "+": value = (left + right) & MASK
    elif op == "-": value = (left - right) & MASK
    elif op == "*": value = (left * right) & MASK
    elif op == "^": value = left ^ right
    elif op == "&": value = left & right
    elif op == "|": value = left | right
    elif op == "/":
        if right == 0: return False, 0
        value = left // right
    elif op == "%":
        if right == 0: return False, 0
        value = left % right
    elif op == "<<":
        if right >= 32: return False, 0
        value = (left << right) & MASK
    elif op == ">>":
        if right >= 32: return False, 0
        value = left >> right
    else: raise AssertionError(op)
    return defined, value & MASK


def eval_b(expr, env: dict[str, int]) -> tuple[bool, bool]:
    op = expr[0]
    if op == "!":
        defined, value = eval_b(expr[1], env)
        return defined, not value
    if op == "&&":
        dl, left = eval_b(expr[1], env)
        if not dl: return False, False
        if not left: return True, False
        dr, right = eval_b(expr[2], env)
        return dr, bool(right) if dr else False
    if op == "||":
        dl, left = eval_b(expr[1], env)
        if not dl: return False, False
        if left: return True, True
        dr, right = eval_b(expr[2], env)
        return dr, bool(right) if dr else False
    dl, left = eval_u(expr[1], env)
    dr, right = eval_u(expr[2], env)
    if not (dl and dr): return False, False
    if op == "==": value = left == right
    elif op == "!=": value = left != right
    elif op == "<": value = left < right
    elif op == "<=": value = left <= right
    elif op == ">": value = left > right
    elif op == ">=": value = left >= right
    else: raise AssertionError(op)
    return True, value


@dataclass(frozen=True)
class Decl:
    name: str
    expr: tuple


@dataclass(frozen=True)
class SetVar:
    name: str
    expr: tuple


@dataclass(frozen=True)
class If:
    cond: tuple
    yes: tuple
    no: tuple


@dataclass(frozen=True)
class Return:
    expr: tuple


Statement = Decl | SetVar | If | Return


def render_statement(stmt: Statement, indent: str = "") -> str:
    if isinstance(stmt, Decl): return f"{indent}unsigned {stmt.name} = {render_u(stmt.expr)};\n"
    if isinstance(stmt, SetVar): return f"{indent}{stmt.name} = {render_u(stmt.expr)};\n"
    if isinstance(stmt, Return): return f"{indent}return {render_u(stmt.expr)};\n"
    yes = "".join(render_statement(child, indent + "  ") for child in stmt.yes)
    no = "".join(render_statement(child, indent + "  ") for child in stmt.no)
    return f"{indent}if ({render_b(stmt.cond)}) {{\n{yes}{indent}}} else {{\n{no}{indent}}}\n"


def render_program(params: tuple[str, ...], body: tuple[Statement, ...]) -> str:
    signature = ", ".join("unsigned " + name for name in params)
    return f"unsigned f({signature}) {{\n" + "".join(render_statement(stmt, "  ") for stmt in body) + "}\n"


def execute(body: tuple[Statement, ...], point_env: dict[str, int]) -> tuple[bool, int | None, list[list[int]]]:
    env = dict(point_env)
    trace: list[list[int]] = []
    next_site = 0

    def block(stmts: tuple[Statement, ...]) -> tuple[bool, int | None, bool]:
        nonlocal next_site
        for stmt in stmts:
            if isinstance(stmt, Decl) or isinstance(stmt, SetVar):
                defined, value = eval_u(stmt.expr, env)
                if not defined: return False, None, True
                env[stmt.name] = value
            elif isinstance(stmt, If):
                site = next_site
                next_site += 1
                defined, value = eval_b(stmt.cond, env)
                if not defined: return False, None, True
                trace.append([site, int(value)])
                defined, result, returned = block(stmt.yes if value else stmt.no)
                if not defined or returned: return defined, result, returned
            elif isinstance(stmt, Return):
                defined, value = eval_u(stmt.expr, env)
                return defined, value if defined else None, True
            else: raise AssertionError(type(stmt))
        return True, None, False

    defined, value, returned = block(body)
    assert returned or not defined
    return defined, value, trace


def random_u(rng: random.Random, variables: tuple[str, ...], depth: int = 0):
    if depth >= 3 or rng.random() < 0.34:
        if rng.random() < 0.72: return u_var(rng.choice(variables))
        return u_const(rng.choice((0, 1, 2, 3, 7, 15, 31, 0x7FFFFFFF, MASK)))
    op = rng.choice(("+", "-", "*", "^", "&", "|", "/", "%", "<<", ">>", "~"))
    if op == "~": return u_unary(random_u(rng, variables, depth + 1))
    left = random_u(rng, variables, depth + 1)
    raw_right = random_u(rng, variables, depth + 1)
    if op in {"/", "%"}:
        right = u_bin("+", u_bin("&", raw_right, u_const(7)), u_const(1))
    elif op in {"<<", ">>"}:
        right = u_bin("&", raw_right, u_const(31))
    else:
        right = raw_right
    return u_bin(op, left, right)


def random_b(rng: random.Random, variables: tuple[str, ...], depth: int = 0):
    if depth < 2 and rng.random() < 0.28:
        op = rng.choice(("&&", "||"))
        return b_bin(op, random_b(rng, variables, depth + 1), random_b(rng, variables, depth + 1))
    if depth < 2 and rng.random() < 0.12:
        return b_not(random_b(rng, variables, depth + 1))
    return b_rel(rng.choice(("==", "!=", "<", "<=", ">", ">=")),
                 random_u(rng, variables, 1), random_u(rng, variables, 1))


def base_body(rng: random.Random, params: tuple[str, ...]) -> tuple[Statement, ...]:
    body: list[Statement] = []
    body.append(Decl("a", random_u(rng, params)))
    body.append(Decl("b", random_u(rng, params + ("a",))))
    body.append(Decl("r", random_u(rng, params + ("a", "b"))))
    for _ in range(rng.randrange(3)):
        variables = params + ("a", "b", "r")
        cond = random_b(rng, variables)
        yes = (SetVar("r", random_u(rng, variables)),)
        no = (SetVar("r", random_u(rng, variables)),)
        body.append(If(cond, yes, no))
    body.append(Return(u_var("r")))
    return tuple(body)


def insert_before_return(body: tuple[Statement, ...], stmt: Statement) -> tuple[Statement, ...]:
    assert isinstance(body[-1], Return)
    return body[:-1] + (stmt, body[-1])


def prepend(body: tuple[Statement, ...], stmt: Statement) -> tuple[Statement, ...]:
    return (stmt,) + body


def case(seed: int, variant: str) -> tuple[dict[str, Any], tuple[Statement, ...], tuple[Statement, ...], tuple[Statement, ...]]:
    rng = random.Random(seed)
    param_count = 2 + rng.randrange(3)
    params = NAMES[:param_count]
    domains: dict[str, list[int]] = {}
    for index, name in enumerate(params):
        values = {0, 1, 3}
        values.add(rng.choice((2, 7, 15, 31, 0x7FFFFFFF, MASK)))
        domains[name] = sorted(values)[:3]
    guard_value = rng.choice(domains["x"])
    outside = rng.choice([value for value in domains["x"] if value != guard_value])
    y_value = rng.choice(domains["y"])
    base = base_body(rng, params)
    original_mutation = If(b_rel("==", u_var("x"), u_const(guard_value)),
                           (SetVar("r", u_bin("-", u_var("r"), u_const(1))),),
                           (SetVar("r", u_var("r")),))
    original = insert_before_return(base, original_mutation)
    reference = base
    candidate = base
    if variant == "repair":
        cond = b_bin("&&", b_rel("==", u_var("x"), u_const(guard_value)),
                     b_rel("==", u_var("y"), u_const(y_value)))
        candidate = insert_before_return(base, If(cond,
            (SetVar("r", u_bin("+", u_var("r"), u_const(1))),),
            (SetVar("r", u_var("r")),)))
    elif variant == "preserve":
        cond = b_bin("&&", b_rel("==", u_var("x"), u_const(outside)),
                     b_rel("==", u_var("y"), u_const(y_value)))
        candidate = insert_before_return(base, If(cond,
            (SetVar("r", u_bin("+", u_var("r"), u_const(1))),),
            (SetVar("r", u_var("r")),)))
    elif variant == "defined":
        poison_name = params[-1]
        poison_value = rng.choice(domains[poison_name])
        poison = Decl("poison", u_bin("/", u_const(1), u_bin("^", u_var(poison_name), u_const(poison_value))))
        candidate = prepend(base, poison)
    elif variant != "accept":
        raise ValueError(variant)
    request = {
        "id": f"holdout-{seed:08x}-{variant}",
        "word_bits": 32,
        "inputs": domains,
        "original": render_program(params, original),
        "candidate": render_program(params, candidate),
        "reference": render_program(params, reference),
        "repair_guard": render_b(b_rel("==", u_var("x"), u_const(guard_value))),
    }
    return request, original, candidate, reference


def oracle(request: dict[str, Any], original, candidate, reference) -> dict[str, Any]:
    names = tuple(request["inputs"])
    points = list(itertools.product(*(request["inputs"][name] for name in names)))
    guard_value = int(request["repair_guard"].split("==")[1].split("u")[0].strip(" ()"))
    bad: list[list[tuple[list[list[int]], tuple[int, ...]]]] = [[], [], []]
    for point in points:
        env = dict(zip(names, point))
        pd, pv, _pt = execute(original, env)
        qd, qv, qt = execute(candidate, env)
        td, tv, _tt = execute(reference, env)
        in_repair = env["x"] == guard_value
        truth = (
            qd,
            (not in_repair) or (qd and td and qv == tv),
            in_repair or (qd and pd and qv == pv),
        )
        for index, ok in enumerate(truth):
            if not ok: bad[index].append((qt, point))
    for index, rows in enumerate(bad):
        if rows:
            trace, point = min(rows, key=lambda row: (row[0], row[1]))
            return {"status": "REFUTED", "witness": {
                "obligation": ("defined", "repair", "preserve")[index],
                "trace": trace, "input": list(point)}}
    return {"status": "ACCEPT", "witness": None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=400)
    args = parser.parse_args()
    if args.cases < 40 or args.cases % 4:
        parser.error("--cases must be a multiple of four and at least 40")
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error("output must be new or empty")
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    records: list[dict[str, Any]] = []
    variants = {name: 0 for name in VARIANTS}
    statuses = {"ACCEPT": 0, "REFUTED": 0}
    compact = 0
    fake_rejections = 0
    max_nodes = 0
    max_points = 0
    for index in range(args.cases):
        variant = VARIANTS[index % 4]
        seed = CAMPAIGN_SEED + index * 104729
        request, original, candidate, reference = case(seed, variant)
        expected = oracle(request, original, candidate, reference)
        cert = produce(request)
        actual = proof_check(request, cert)
        direct = evaluate_topological(request)
        if actual["status"] != expected["status"] or actual["witness"] != expected["witness"]:
            raise AssertionError((request["id"], expected, actual))
        if direct["status"] != expected["status"] or direct["witness"] != expected["witness"]:
            raise AssertionError((request["id"], expected, direct))
        if variant == "accept" and actual["status"] != "ACCEPT":
            raise AssertionError((request["id"], "expected accept", actual))
        if variant != "accept" and actual["status"] != "REFUTED":
            raise AssertionError((request["id"], "expected refutation", actual))
        if variant != "accept" and actual["witness"]["obligation"] != variant:
            raise AssertionError((request["id"], variant, actual))
        if actual["status"] == "REFUTED":
            witness = produce_refutation(request, actual["witness"])
            compact_result = refutation_check(request, witness)
            if compact_result["witness"] != expected["witness"]:
                raise AssertionError((request["id"], expected, compact_result))
            compact += 1
        else:
            first = [request["inputs"][name][0] for name in request["inputs"]]
            fake = produce_refutation(request, {"obligation": "defined", "trace": [], "input": first})
            try:
                refutation_check(request, fake)
            except (Invalid, Unsupported):
                fake_rejections += 1
            else:
                raise AssertionError((request["id"], "forged refutation accepted"))
        variants[variant] += 1
        statuses[actual["status"]] += 1
        max_nodes = max(max_nodes, actual["checked_nodes"])
        max_points = max(max_points, len(cert["points"]))
        save_request(out / "inputs" / f"{request['id']}.json", request)
        records.append({
            "id": request["id"], "seed": seed, "variant": variant,
            "status": actual["status"], "witness": actual["witness"],
            "nodes": actual["checked_nodes"], "points": len(cert["points"]),
            "certificate_bytes": len(canonical(cert)),
        })
    record_digest = hashlib.sha256(canonical(records)).hexdigest()
    summary = {
        "schema": "holdout-differential-v2",
        "outcome": "PASS",
        "campaign_seed": CAMPAIGN_SEED,
        "cases": args.cases,
        "variants": variants,
        "statuses": statuses,
        "oracle_agreements": len(records),
        "topological_agreements": len(records),
        "compact_refutations_verified": compact,
        "forged_refutations_rejected": fake_rejections,
        "min_nodes": min(row["nodes"] for row in records),
        "max_nodes": max_nodes,
        "point_counts": {str(value): sum(row["points"] == value for row in records) for value in sorted({row["points"] for row in records})},
        "min_points": min(row["points"] for row in records),
        "max_points": max_points,
        "median_nodes": statistics.median(row["nodes"] for row in records),
        "median_certificate_bytes": statistics.median(row["certificate_bytes"] for row in records),
        "record_index_sha256": record_digest,
        "wall_seconds": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "scope": (
            "Deterministic post hoc grammar-generated loop-free scalar requests with an independent AST interpreter; "
            "not Codeflaws and not evidence of unrestricted-C generality."
        ),
    }
    save(out / "cases.json", records)
    save(out / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
