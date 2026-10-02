"""Untrusted producer for finite semantic proof DAG certificates.

The producer may use symbolic compilation and exhaustive finite evaluation.  The
receiver does not import this module.  Certificates bind to exact source text,
carry a canonical circuit, and attach one semantic vector to every circuit node.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any, Callable

from producer import Producer, ProducerError, value as producer_value

SCHEMA = "finite-semantic-proof-dag-v1"
ROLES = ("original", "candidate", "reference")
OBLIGATIONS = ("defined", "repair", "preserve")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def source_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sorts(nodes: list[tuple]) -> list[str]:
    sorts: list[str] = []
    for node in nodes:
        op = node[0]
        if op == "b": sort = "bool"
        elif op in {"u", "input", "inv", "+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^"}: sort = "u32"
        elif op in {"not", "and", "or", "==", "!=", "<", "<=", ">", ">="}: sort = "bool"
        elif op == "ite": sort = sorts[node[2]]
        else: raise ValueError(f"unknown producer node {op!r}")
        sorts.append(sort)
    return sorts


def _node_record(index: int, node: tuple, sort: str, vector: list[Any]) -> dict[str, Any]:
    op, *args = node
    record: dict[str, Any] = {"id": index, "op": op, "sort": sort, "vector": vector}
    if op in {"b", "u", "input"}: record["data"] = args[0]
    else: record["children"] = list(args)
    return record



def _evaluate_all_nodes(nodes: list[tuple], env: dict[str, int], tick: Callable[[str, int], None]) -> list[Any]:
    """Evaluate a topologically ordered producer DAG once at one point.

    The previous implementation called ``DAG.evaluate`` separately for every
    root node, creating a fresh memo table each time.  A left-deep DAG could
    therefore cause quadratic node visits per point even though the emitted
    vectors contain only one value per node and point.
    """
    values: list[Any] = []
    for node in nodes:
        tick("producer_vector_cells", 1)
        op, *args = node
        if op in {"b", "u"}:
            result = args[0]
        elif op == "input":
            result = env[args[0]]
        elif op == "and":
            result = bool(values[args[0]] and values[args[1]])
        elif op == "or":
            result = bool(values[args[0]] or values[args[1]])
        elif op == "ite":
            result = values[args[1]] if values[args[0]] else values[args[2]]
        else:
            result = producer_value(op, tuple(values[child] for child in args))
        values.append(result)
    return values

def produce(request: dict, count: Callable[[str, int], None] | None = None) -> dict:
    tick = count or (lambda _kind, _n=1: None)
    try:
        model = Producer(request, tick)
    except RecursionError as exc:
        raise ProducerError("AST recursion safety") from exc
    names = list(request["inputs"])
    points = [list(p) for p in itertools.product(*(request["inputs"][n] for n in names))]
    if len(points) > 4096:
        raise ValueError("finite domain bound")
    sorts = _sorts(model.dag.nodes)
    vectors: list[list[Any]] = [[] for _ in model.dag.nodes]
    for point in points:
        env = dict(zip(names, point))
        point_values = _evaluate_all_nodes(model.dag.nodes, env, tick)
        for node_id, node_value in enumerate(point_values):
            vectors[node_id].append(node_value)
    nodes = [_node_record(i, n, sorts[i], vectors[i]) for i, n in enumerate(model.dag.nodes)]
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
        "source_sha256": {role: source_digest(request[role]) for role in ROLES}
                         | {"repair_guard": source_digest(request["repair_guard"])},
        "nodes": nodes,
        "role_roots": role_roots,
        "guard_root": model.guard,
        "obligation_roots": dict(zip(OBLIGATIONS, model.roots)),
    }
    body["certificate_sha256"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    certificate = produce(request)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(certificate, indent=2) + "\n")


if __name__ == "__main__":
    main()
