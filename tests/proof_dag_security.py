"""Deterministic fail-closed and grammar-coverage regression suite.

This suite complements the measured mutation campaign.  It exercises request
bounds, parser rejection paths, producer/checker limit parity, all local
operators, and the checker's static import boundary.  It uses only benign,
self-contained programs in the declared fragment.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from checker import Session
from fixture_oracle import request as fixture_request
from proof_dag_checker import Invalid, Unsupported, canonical_bytes, check, digest, exact_equal, load_json_strict
from proof_dag_producer import produce

MASK = (1 << 32) - 1
ROLES = ("original", "candidate", "reference")


def rehash(cert: dict) -> None:
    cert.pop("certificate_sha256", None)
    cert["certificate_sha256"] = hashlib.sha256(canonical_bytes(cert)).hexdigest()


def bind_sources(cert: dict, request: dict) -> dict:
    out = copy.deepcopy(cert)
    out["source_sha256"] = {role: digest(request[role]) for role in ROLES} | {
        "repair_guard": digest(request["repair_guard"])
    }
    rehash(out)
    return out


def direct_result(request: dict) -> dict:
    session = Session(request)
    names = list(request["inputs"])
    points = itertools.product(*(request["inputs"][n] for n in names))
    points = list(points)
    for index, obligation in enumerate(("defined", "repair", "preserve")):
        bad = []
        for point in points:
            env = dict(zip(names, point))
            if not session.predicate(index, env):
                bad.append((session.run("candidate", env)[2], point))
        if bad:
            trace, point = min(bad)
            return {
                "status": "REFUTED",
                "witness": {
                    "obligation": obligation,
                    "trace": [list(entry) for entry in trace],
                    "input": list(point),
                },
            }
    return {"status": "ACCEPT", "witness": None}


def program(parameters: tuple[str, ...], expression: str | None = None, condition: str | None = None) -> str:
    signature = ", ".join("unsigned " + name for name in parameters)
    if expression is not None:
        body = f"unsigned r = {expression};\n"
    elif condition is not None:
        body = f"unsigned r = 0u;\nif ({condition}) {{ r = 1u; }} else {{ r = 2u; }}\n"
    else:
        raise ValueError("expression or condition required")
    return f"unsigned f({signature}) {{\n{body}return r;\n}}\n"


def accepted_request(identifier: str, source: str, inputs: dict[str, list[int]], guard: str | None = None) -> dict:
    return {
        "id": identifier,
        "word_bits": 32,
        "inputs": inputs,
        "original": source,
        "candidate": source,
        "reference": source,
        "repair_guard": guard or (next(iter(inputs)) + " == 0u"),
    }


def operator_probes() -> tuple[list[dict], set[str]]:
    params = ("x", "y", "z", "t")
    inputs = {name: [0, 1, 2] for name in params}
    expressions = {
        "add": "x + y",
        "subtract": "x - y",
        "multiply": "x * (y + 1u)",
        "divide": "(x + 4u) / (y + 1u)",
        "remainder": "(x + 4u) % (y + 1u)",
        "left-shift": "x << y",
        "right-shift": "x >> y",
        "bit-and": "x & y",
        "bit-or": "x | y",
        "bit-xor": "x ^ y",
        "bit-invert": "~x",
    }
    conditions = {
        "equal": "x == y",
        "not-equal": "x != y",
        "less": "x < y",
        "less-equal": "x <= y",
        "greater": "x > y",
        "greater-equal": "x >= y",
        "logical-and": "(x != 0u) && (y != 0u)",
        "logical-or": "(x == 0u) || (y == 0u)",
        "logical-not": "!(x == y)",
        "short-circuit-totality": "(x == 0u) || ((y / x) > 0u)",
    }
    records = []
    seen: set[str] = set()
    for name, expr in expressions.items():
        src = program(params, expression=expr)
        req = accepted_request("operator-" + name, src, inputs)
        cert = produce(req)
        got = check(req, cert)
        direct = direct_result(req)
        assert got["status"] == "ACCEPT" and got["witness"] is None
        assert direct == {"status": "ACCEPT", "witness": None}
        seen.update(node["op"] for node in cert["nodes"])
        records.append({"id": req["id"], "status": got["status"], "nodes": len(cert["nodes"]), "points": len(cert["points"])})
    for name, cond in conditions.items():
        src = program(params, condition=cond)
        req = accepted_request("operator-" + name, src, inputs)
        cert = produce(req)
        got = check(req, cert)
        direct = direct_result(req)
        assert got["status"] == "ACCEPT" and got["witness"] is None
        assert direct == {"status": "ACCEPT", "witness": None}
        seen.update(node["op"] for node in cert["nodes"])
        records.append({"id": req["id"], "status": got["status"], "nodes": len(cert["nodes"]), "points": len(cert["points"])})
    required = {"b", "u", "input", "inv", "+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^",
                "not", "and", "or", "==", "!=", "<", "<=", ">", ">=", "ite"}
    missing = sorted(required - seen)
    assert not missing, missing
    return records, seen


def nested_if(depth: int) -> str:
    inner = "r = r + 1u;"
    for _ in range(depth):
        inner = f"if (x == 0u) {{ {inner} }} else {{ r = r; }}"
    return "unsigned f(unsigned x, unsigned y, unsigned z, unsigned t) {\nunsigned r = x;\n" + inner + "\nreturn r;\n}\n"


def many_if(count: int) -> str:
    statements = "\n".join("if (x == 0u) { r = r; } else { r = r; }" for _ in range(count))
    return "unsigned f(unsigned x, unsigned y, unsigned z, unsigned t) {\nunsigned r = x;\n" + statements + "\nreturn r;\n}\n"


def many_locals(count: int) -> str:
    declarations = "\n".join(f"unsigned a{i} = x + {i}u;" for i in range(count))
    last = f"a{count - 1}" if count else "x"
    return "unsigned f(unsigned x, unsigned y, unsigned z, unsigned t) {\n" + declarations + f"\nunsigned r = {last};\nreturn r;\n}}\n"


def rejection_cases() -> list[dict]:
    base = fixture_request(1, "correct")
    base_cert = produce(base)
    records: list[dict] = []

    def expect(name: str, request, certificate=None, source_rebind: bool = False) -> None:
        cert = copy.deepcopy(base_cert if certificate is None else certificate)
        if source_rebind:
            cert = bind_sources(cert, request)
        try:
            result = check(request, cert)
        except (Invalid, Unsupported) as exc:
            records.append({"case": name, "status": "REJECTED", "reason": str(exc)})
            return
        raise AssertionError(f"{name} unexpectedly returned {result}")

    expect("request-not-dict", [])
    req = copy.deepcopy(base); req["extra"] = 1; expect("request-extra-field", req)
    req = copy.deepcopy(base); req.pop("reference"); expect("request-missing-field", req)
    req = copy.deepcopy(base); req["id"] = ""; expect("id-empty", req)
    req = copy.deepcopy(base); req["id"] = 7; expect("id-not-string", req)
    req = copy.deepcopy(base); req["id"] = "x" * 65; expect("id-too-long", req)
    req = copy.deepcopy(base); req["word_bits"] = True; expect("word-bits-bool", req)
    req = copy.deepcopy(base); req["word_bits"] = 64; expect("word-bits-64", req)
    req = copy.deepcopy(base); req["inputs"] = []; expect("inputs-not-dict", req)
    req = copy.deepcopy(base); req["inputs"] = {}; expect("inputs-empty", req)
    req = copy.deepcopy(base); req["inputs"] = {f"x{i}": [0] for i in range(9)}; expect("inputs-nine", req)
    req = copy.deepcopy(base); req["inputs"] = {"if": [0], "y": [0], "z": [0], "t": [0]}; expect("input-reserved-name", req)
    req = copy.deepcopy(base); req["inputs"] = {"__x": [0], "y": [0], "z": [0], "t": [0]}; expect("input-reserved-pattern", req)
    req = copy.deepcopy(base); req["inputs"]["x"] = []; expect("domain-empty", req)
    req = copy.deepcopy(base); req["inputs"]["x"] = list(range(65)); expect("domain-too-many-values", req)
    req = copy.deepcopy(base); req["inputs"]["x"] = [False, 1]; expect("domain-bool", req)
    req = copy.deepcopy(base); req["inputs"]["x"] = [None]; expect("domain-null", req)
    req = copy.deepcopy(base); req["inputs"]["x"] = [1.5]; expect("domain-float", req)
    req = copy.deepcopy(base); req["inputs"]["x"] = [[]]; expect("domain-list-element", req)
    req = copy.deepcopy(base); req["inputs"]["x"] = [{}]; expect("domain-object-element", req)
    req = copy.deepcopy(base); req["inputs"]["x"] = [-1, 0]; expect("domain-negative", req)
    req = copy.deepcopy(base); req["inputs"]["x"] = [0, MASK + 1]; expect("domain-overflow", req)
    req = copy.deepcopy(base); req["inputs"]["x"] = [0, 0]; expect("domain-duplicate", req)
    req = copy.deepcopy(base); req["inputs"]["x"] = [1, 0]; expect("domain-unsorted", req)
    req = copy.deepcopy(base); req["inputs"] = {name: list(range(8)) for name in ("a", "b", "c", "d", "e")}; expect("domain-product", req)
    req = copy.deepcopy(base); req["candidate"] = 1; expect("source-not-string", req)

    def source_case(name: str, source: str) -> None:
        req = copy.deepcopy(base); req["candidate"] = source; expect(name, req, source_rebind=True)

    source_case("source-non-ascii", base["candidate"] + "é")
    source_case("source-backslash", base["candidate"].replace("return r;", "return r;\\"))
    source_case("source-trigraph", base["candidate"] + "??=")
    source_case("source-token-outside-fragment", base["candidate"].replace("return r;", "return @r;"))
    source_case("source-loop", base["candidate"].replace("return r;", "while (x == 0u) { r = r; } return r;"))
    source_case("source-call", base["candidate"].replace("return r;", "r = g(x); return r;"))
    source_case("nested-declaration", base["candidate"].replace("scratch = scratch + 1u;", "unsigned q = x; scratch = scratch + q;"))
    source_case("early-return", base["candidate"].replace("scratch = scratch + 1u;", "return scratch;"))
    source_case("missing-else", "unsigned f(unsigned x, unsigned y, unsigned z, unsigned t) { unsigned r = x; if (x == 0u) { r = y; } return r; }")
    source_case("uninitialized-variable", "unsigned f(unsigned x, unsigned y, unsigned z, unsigned t) { unsigned r = q; return r; }")
    source_case("boolean-used-as-number", "unsigned f(unsigned x, unsigned y, unsigned z, unsigned t) { unsigned r = (x == y) + 1u; return r; }")
    source_case("parameter-order", base["candidate"].replace("unsigned x, unsigned y", "unsigned y, unsigned x", 1))
    source_case("source-too-many-lines", base["candidate"] + "\n" * 251)
    source_case("source-too-long", base["candidate"] + " " * 17000)
    source_case("token-bound", "unsigned f(unsigned x, unsigned y, unsigned z, unsigned t) { unsigned r = " + "+".join(["x"] * 2050) + "; return r; }")
    source_case("expression-depth", "unsigned f(unsigned x, unsigned y, unsigned z, unsigned t) { unsigned r = " + "~" * 65 + "x; return r; }")
    source_case("block-depth", nested_if(65))
    source_case("branch-count", many_if(129))
    source_case("binding-count", many_locals(68))

    req = copy.deepcopy(base); req["repair_guard"] = "x / y > 0u"; expect("guard-partial", req, source_rebind=True)
    req = copy.deepcopy(base); req["repair_guard"] = "x + 1u"; expect("guard-not-boolean", req, source_rebind=True)
    assert all(record["status"] == "REJECTED" for record in records)
    return records


def certificate_type_rejection_cases() -> list[dict]:
    """Exercise JSON Boolean/number aliases at every nested binding layer.

    Ordinary Python equality equates ``True`` with ``1`` and ``False`` with
    ``0``.  These controls recompute the outer certificate digest so rejection
    must come from exact typed reconstruction rather than stale-hash detection.
    """
    request = fixture_request(1, "correct")
    base = produce(request)
    records: list[dict] = []

    def expect(name: str, mutate) -> None:
        cert = copy.deepcopy(base)
        mutate(cert)
        rehash(cert)
        try:
            result = check(request, cert)
        except (Invalid, Unsupported) as exc:
            records.append({"case": name, "status": "REJECTED", "reason": str(exc)})
            return
        raise AssertionError(f"{name} unexpectedly returned {result}")

    expect("domain-integer-one-to-boolean", lambda cert: cert["domains"]["x"].__setitem__(1, True))
    expect("point-integer-one-to-boolean", lambda cert: cert["points"][27].__setitem__(0, True))
    expect("node-id-one-to-boolean", lambda cert: cert["nodes"][1].__setitem__("id", True))
    expect("obligation-root-zero-to-boolean", lambda cert: cert["obligation_roots"].__setitem__("defined", False))
    expect("unsigned-data-one-to-boolean", lambda cert: cert["nodes"][9].__setitem__("data", True))
    expect("boolean-data-true-to-integer", lambda cert: cert["nodes"][0].__setitem__("data", 1))
    expect("trace-site-zero-to-boolean", lambda cert: cert["role_roots"]["candidate"]["trace_events"][0].__setitem__("site", False))

    assert not exact_equal(True, 1)
    assert not exact_equal(False, 0)
    assert exact_equal({"x": [0, 1]}, {"x": [0, 1]})
    assert all(record["status"] == "REJECTED" for record in records)
    return records


def json_text_rejection_cases() -> list[dict]:
    cases = {
        "duplicate-object-key": '{"x": 1, "x": 2}',
        "nan-constant": '{"x": NaN}',
        "infinity-constant": '{"x": Infinity}',
        "malformed-json": '{"x":',
    }
    records = []
    for name, text in cases.items():
        try:
            load_json_strict(text)
        except Invalid as exc:
            records.append({"case": name, "status": "REJECTED", "reason": str(exc)})
        else:
            raise AssertionError(f"{name} unexpectedly decoded")
    assert load_json_strict('{"x": [0, 1], "ok": true}') == {"x": [0, 1], "ok": True}
    return records


def acceptance_boundaries() -> list[dict]:
    records = []

    # 68 locals (67 temporaries plus r) and four parameters reach the 72-name cap exactly.
    src = many_locals(67)
    req = accepted_request("boundary-bindings-72", src, {name: [0, 1] for name in ("x", "y", "z", "t")})
    cert = produce(req); result = check(req, cert)
    assert result["status"] == "ACCEPT"
    records.append({"case": "bindings-72", "status": result["status"], "nodes": len(cert["nodes"]), "points": len(cert["points"])})

    # Maximum per-variable domain and maximum Cartesian product are both admitted.
    src = program(("x", "y"), expression="x + y")
    req = accepted_request("boundary-domain-4096", src, {"x": list(range(64)), "y": list(range(64))})
    cert = produce(req); result = check(req, cert)
    assert result["status"] == "ACCEPT" and len(cert["points"]) == 4096
    records.append({"case": "domain-4096", "status": result["status"], "nodes": len(cert["nodes"]), "points": len(cert["points"])})

    params = tuple(f"x{i}" for i in range(8))
    src = program(params, expression="x0 + x7")
    req = accepted_request("boundary-eight-parameters", src, {name: [0, 1] for name in params})
    cert = produce(req); result = check(req, cert)
    assert result["status"] == "ACCEPT"
    records.append({"case": "parameters-8", "status": result["status"], "nodes": len(cert["nodes"]), "points": len(cert["points"])})
    return records


def import_boundary() -> dict:
    path = ROOT / "src" / "proof_dag_checker.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = sorted(imported & {"producer", "proof_dag_producer", "checker"})
    assert not forbidden
    return {"checker": str(path.relative_to(ROOT)), "imports": sorted(imported), "forbidden_imports": forbidden}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    probes, seen = operator_probes()
    rejected = rejection_cases()
    type_rejected = certificate_type_rejection_cases()
    json_rejected = json_text_rejection_cases()
    accepted = acceptance_boundaries()
    boundary = import_boundary()
    result = {
        "schema": "proof-dag-security-regression-v2",
        "outcome": "PASS",
        "operator_probes": len(probes),
        "operator_probe_records": probes,
        "operator_coverage": sorted(seen),
        "request_rejection_cases": len(rejected),
        "request_rejections": rejected,
        "certificate_type_rejection_cases": len(type_rejected),
        "certificate_type_rejections": type_rejected,
        "json_text_rejection_cases": len(json_rejected),
        "json_text_rejections": json_rejected,
        "acceptance_boundary_cases": len(accepted),
        "acceptance_boundaries": accepted,
        "rejection_reason_counts": dict(sorted(Counter(row["reason"] for row in rejected).items())),
        "import_boundary": boundary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "outcome": result["outcome"],
        "operator_probes": result["operator_probes"],
        "operators_covered": len(result["operator_coverage"]),
        "request_rejection_cases": result["request_rejection_cases"],
        "certificate_type_rejection_cases": result["certificate_type_rejection_cases"],
        "json_text_rejection_cases": result["json_text_rejection_cases"],
        "acceptance_boundary_cases": result["acceptance_boundary_cases"],
    }, indent=2))


if __name__ == "__main__":
    main()
