"""Run the structured proof-DAG study and deterministic stress campaign."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import itertools
import json
import math
import os
import resource
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
from checker import Session
from fixture_oracle import NAMES, VARIANTS, request as fixture_request, exhaustive, least_violation
from proof_dag_checker import (
    Invalid, Unsupported, OBLIGATIONS, canonical_bytes, check as proof_check,
    evaluate_topological,
)
from proof_dag_producer import produce
from refutation_witness_checker import check as refutation_check
from refutation_witness_producer import produce as produce_refutation

MASK = (1 << 32) - 1


def save(path: Path, value, *, sort_keys: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=sort_keys) + "\n")


def save_request(path: Path, request: dict) -> None:
    """Persist a receiver request without reordering its authoritative inputs.

    JSON object member order is the request's coordinate order in this artifact.
    Sorting nested keys would silently turn x,y,z,t into t,x,y,z and therefore
    change the finite function being checked after reload.
    """
    save(path, request, sort_keys=False)


def rehash(cert: dict) -> None:
    cert.pop("certificate_sha256", None)
    cert["certificate_sha256"] = hashlib.sha256(canonical_bytes(cert)).hexdigest()


def mutate_refutation(cert: dict, kind: str) -> dict:
    """Create one targeted invalid compact-refutation certificate."""
    c = copy.deepcopy(cert)
    rehash_after = True
    first = c["input_order"][0]
    if kind == "input-bool":
        c["input"][0] = True
    elif kind == "input-outside":
        c["input"][0] = -1
    elif kind == "obligation":
        c["obligation"] = "unknown"
    elif kind == "trace-type":
        c["trace"] = "not-a-trace"
    elif kind == "trace-content":
        if c["trace"]:
            c["trace"][0][1] = 1 - c["trace"][0][1]
        else:
            c["trace"] = [[0, 0]]
    elif kind == "source-binding":
        c["source_sha256"]["candidate"] = "0" * 64
    elif kind == "domain-binding":
        c["domains"][first] = list(reversed(c["domains"][first]))
    elif kind == "request-id":
        c["request_id"] += "-mutated"
    elif kind == "extra-field":
        c["unexpected"] = 1
    elif kind == "digest":
        c["request_id"] += "-stale"
        rehash_after = False
    else:
        raise ValueError(kind)
    if rehash_after:
        rehash(c)
    return c


def counter():
    values = Counter()
    def tick(kind, n=1): values[kind] += n
    return values, tick


def direct_result(req: dict):
    session = Session(req)
    names = list(req["inputs"])
    points = list(itertools.product(*(req["inputs"][n] for n in names)))
    for j, obligation in enumerate(("defined", "repair", "preserve")):
        bad = []
        for point in points:
            env = dict(zip(names, point))
            if not session.predicate(j, env):
                bad.append((session.run("candidate", env)[2], point))
        if bad:
            trace, point = min(bad)
            return {"status": "REFUTED", "witness": {"obligation": obligation,
                    "trace": [list(v) for v in trace], "input": list(point)}}
    return {"status": "ACCEPT", "witness": None}


def stress_request(index: int) -> tuple[dict, list[dict]]:
    variant = VARIANTS[index % len(VARIANTS)]
    a = 1 + (index * 17) % 11
    b = 1 + (index * 29) % 13
    c = (index * 37) % 17
    domains = {name: [0, 1, 2] for name in NAMES}
    params = ", ".join("unsigned " + n for n in NAMES)
    ref_expr = f"((x + {a}u) * (y + {b}u)) ^ (z + {c}u)"
    cand_expr = f"(z + {c}u) ^ (({b}u + y) * ({a}u + x))"
    reference = f"unsigned f({params}) {{\nunsigned r = {ref_expr};\nreturn r;\n}}\n"
    original = f"unsigned f({params}) {{\nunsigned r = {ref_expr};\nif (x == 0u) {{ r = r - 1u; }} else {{ r = r; }}\nreturn r;\n}}\n"
    prefix = "unsigned scratch = t;\nif ((t & 1u) == 0u) { scratch = scratch + 1u; } else { scratch = scratch + 2u; }\n"
    candidate_body = prefix + f"unsigned r = {cand_expr};"
    if variant == "overfit":
        candidate_body += "\nif ((x == 0u) && (y == 2u)) { r = r + 1u; } else { r = r; }"
    elif variant == "regression":
        candidate_body += "\nif ((x == 2u) && (z == 2u)) { r = r + 1u; } else { r = r; }"
    elif variant == "undefined":
        candidate_body = "unsigned unused = 1u / (t ^ 2u);\n" + candidate_body
    candidate = f"unsigned f({params}) {{\n{candidate_body}\nreturn r;\n}}\n"
    req = {"id": f"stress-{index + 1:03d}-{variant}", "word_bits": 32,
           "inputs": domains, "original": original, "candidate": candidate,
           "reference": reference, "repair_guard": "x == 0u"}
    rows = []
    for point in itertools.product(*domains.values()):
        x, y, z, t = point
        ref = ((((x + a) & MASK) * ((y + b) & MASK)) & MASK) ^ ((z + c) & MASK)
        orig = (ref - 1) & MASK if x == 0 else ref
        undefined = variant == "undefined" and t == 2
        trace = [] if undefined else [[0, int((t & 1) == 0)]]
        wrong = False
        if not undefined and variant == "overfit":
            wrong = x == 0 and y == 2; trace.append([1, int(wrong)])
        elif not undefined and variant == "regression":
            wrong = x == 2 and z == 2; trace.append([1, int(wrong)])
        cand = None if undefined else (ref + int(wrong)) & MASK
        truth = [cand is not None,
                 x != 0 or cand is not None and cand == ref,
                 x == 0 or cand is not None and cand == orig]
        rows.append({"input": list(point), "trace": trace, "truth": [bool(v) for v in truth]})
    return req, rows


def oracle_witness(rows):
    for j, obligation in enumerate(("defined", "repair", "preserve")):
        bad = [r for r in rows if not r["truth"][j]]
        if bad:
            row = min(bad, key=lambda r: (r["trace"], r["input"]))
            return {"obligation": obligation, "trace": row["trace"], "input": row["input"]}
    return None


def mutate(cert: dict, kind: str, seed: int) -> dict:
    """Create one targeted invalid certificate.

    Except for ``certificate-digest``, each mutant receives a fresh outer digest.
    This prevents the digest check from masking topology, binding, schema, or
    local-semantic checks deeper in the receiver.
    """
    c = copy.deepcopy(cert)
    rehash_after = True
    compound = [n for n in c["nodes"] if "children" in n]
    data_nodes = [n for n in c["nodes"] if "data" in n]
    bool_nodes = [n for n in c["nodes"] if n["sort"] == "bool"]
    u32_nodes = [n for n in c["nodes"] if n["sort"] == "u32"]
    candidate_events = c["role_roots"]["candidate"]["trace_events"]

    if kind == "vector":
        node = u32_nodes[seed % len(u32_nodes)]
        cell = seed % len(c["points"])
        node["vector"][cell] = (node["vector"][cell] + 1) & MASK
    elif kind == "topology-op":
        node = compound[seed % len(compound)]
        node["op"] = "^" if node["op"] != "^" else "+"
    elif kind == "topology-child":
        node = compound[seed % len(compound)]
        old = node["children"][0]
        node["children"][0] = 0 if old != 0 else 1
    elif kind.startswith("source-"):
        role = kind.removeprefix("source-")
        c["source_sha256"][role] = "0" * 64
    elif kind.startswith("root-"):
        obligation = kind.removeprefix("root-")
        c["obligation_roots"][obligation] = (c["obligation_roots"][obligation] + 1) % len(c["nodes"])
    elif kind == "guard-root":
        c["guard_root"] = (c["guard_root"] + 1) % len(c["nodes"])
    elif kind == "role-output":
        c["role_roots"]["candidate"]["output"] = (c["role_roots"]["candidate"]["output"] + 1) % len(c["nodes"])
    elif kind == "role-defined":
        c["role_roots"]["candidate"]["defined"] = (c["role_roots"]["candidate"]["defined"] + 1) % len(c["nodes"])
    elif kind == "trace-site":
        candidate_events[seed % len(candidate_events)]["site"] += 1
    elif kind == "trace-reachable":
        event = candidate_events[seed % len(candidate_events)]
        event["reachable"] = (event["reachable"] + 1) % len(c["nodes"])
    elif kind == "trace-guard":
        event = candidate_events[seed % len(candidate_events)]
        event["guard"] = (event["guard"] + 1) % len(c["nodes"])
    elif kind == "vector-length":
        node = c["nodes"][seed % len(c["nodes"])]
        node["vector"] = node["vector"][:-1]
    elif kind == "vector-type":
        node = bool_nodes[seed % len(bool_nodes)]
        node["vector"][seed % len(c["points"])] = 0
    elif kind == "node-sort":
        node = c["nodes"][2 + seed % max(1, len(c["nodes"]) - 2)]
        node["sort"] = "u32" if node["sort"] == "bool" else "bool"
    elif kind == "node-id":
        node = c["nodes"][2 + seed % max(1, len(c["nodes"]) - 2)]
        node["id"] += 1
    elif kind == "node-data":
        node = data_nodes[seed % len(data_nodes)]
        if node["op"] == "b": node["data"] = not node["data"]
        elif node["op"] == "u": node["data"] = (node["data"] + 1) & MASK
        else: node["data"] = str(node["data"]) + "_mutated"
    elif kind == "node-extra-field":
        c["nodes"][seed % len(c["nodes"])]["unexpected"] = 1
    elif kind == "node-missing-field":
        c["nodes"][2 + seed % max(1, len(c["nodes"]) - 2)].pop("sort")
    elif kind == "node-count":
        c["nodes"].pop()
    elif kind == "point-order":
        c["points"][0], c["points"][1] = c["points"][1], c["points"][0]
    elif kind == "point-value":
        c["points"][0][0] = (c["points"][0][0] + 1) & MASK
    elif kind == "domain-binding":
        first = c["input_order"][0]
        c["domains"][first] = list(c["domains"][first])
        c["domains"][first][-1] = (c["domains"][first][-1] + 1) & MASK
    elif kind == "request-id":
        c["request_id"] += "-mutated"
    elif kind == "extra-top-field":
        c["unexpected"] = 1
    elif kind == "certificate-digest":
        node = u32_nodes[seed % len(u32_nodes)]
        node["vector"][seed % len(c["points"])] = (node["vector"][seed % len(c["points"])] + 1) & MASK
        rehash_after = False
    else:
        raise ValueError(kind)
    if rehash_after:
        rehash(c)
    return c

def percentile(values, p):
    if not values: return None
    s = sorted(values); k = (len(s)-1)*p; lo=math.floor(k); hi=math.ceil(k)
    return s[lo] if lo==hi else s[lo]*(hi-k)+s[hi]*(k-lo)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "proof-data")
    args = parser.parse_args(); out=args.output.resolve()
    for d in ("fixture-inputs", "fixture-certificates", "stress-certificates", "stress-inputs", "controls",
              "refutation-witnesses", "refutation-controls"):
        (out/d).mkdir(parents=True,exist_ok=True)
    fixture_records=[]; stress_records=[]; timing=[]
    proof_ops_all=Counter(); proof_ops_correct=Counter(); topological_ops_correct=Counter()
    rebuild_internal_ops=Counter(); rebuild_outer_ops=Counter()
    refutation_records=[]; refutation_certificates=[]; acceptance_misuse_controls=[]
    fixture_certs=[]
    for case in range(1,21):
        for variant in VARIANTS:
            req=fixture_request(case,variant); expected=least_violation(exhaustive(case,variant))
            save_request(out/"fixture-inputs"/(req["id"]+".json"), req)
            t0=time.perf_counter_ns(); cert=produce(req); produce_ns=time.perf_counter_ns()-t0
            save(out/"fixture-certificates"/(req["id"]+".json"),cert)
            proof_counts,tick=counter(); t0=time.perf_counter_ns(); got=proof_check(req,cert,tick); check_ns=time.perf_counter_ns()-t0
            proof_ops_all.update(proof_counts)
            topo_counts,tick=counter(); t0=time.perf_counter_ns(); topological=evaluate_topological(req,tick); topological_ns=time.perf_counter_ns()-t0
            t0=time.perf_counter_ns(); session_direct=direct_result(req); session_ns=time.perf_counter_ns()-t0
            assert got["witness"]==expected and topological["witness"]==expected and session_direct["witness"]==expected
            assert got["status"]==topological["status"]==session_direct["status"]
            witness_bytes=None; witness_ms=None; witness_cells=None
            if got["status"]=="REFUTED":
                witness_cert=produce_refutation(req,got["witness"]); save(out/"refutation-witnesses"/(req["id"]+".json"),witness_cert)
                witness_counts,tick=counter(); t0=time.perf_counter_ns(); witness_result=refutation_check(req,witness_cert,tick); witness_ns=time.perf_counter_ns()-t0
                assert witness_result["witness"]==got["witness"]
                witness_bytes=len(canonical_bytes(witness_cert)); witness_ms=witness_ns/1e6; witness_cells=witness_counts["refutation_cells"]
                refutation_records.append({"id":req["id"],"population":"fixture","certificate_bytes":witness_bytes,"full_certificate_bytes":len(canonical_bytes(cert)),
                    "check_ms":witness_ms,"checked_cells":witness_cells,"full_proof_cells":got["checked_cells"]})
                refutation_certificates.append((req,witness_cert))
            else:
                first_point=[req["inputs"][name][0] for name in req["inputs"]]
                fake=produce_refutation(req,{"obligation":OBLIGATIONS[0],"input":first_point,"trace":[]})
                try:
                    refutation_check(req,fake); misuse_status="MISSED"; misuse_reason="accepted"
                except (Invalid,Unsupported) as exc:
                    misuse_status="REJECTED"; misuse_reason=str(exc)
                acceptance_misuse_controls.append({"id":req["id"],"status":misuse_status,"reason":misuse_reason})
            record={"id":req["id"],"case":case,"variant":variant,"status":got["status"],"witness":got["witness"],
                    "nodes":len(cert["nodes"]),"points":len(cert["points"]),"certificate_bytes":len(canonical_bytes(cert)),
                    "produce_ms":produce_ns/1e6,"check_ms":check_ns/1e6,"topological_ms":topological_ns/1e6,
                    "session_direct_ms":session_ns/1e6,"refutation_certificate_bytes":witness_bytes,
                    "refutation_check_ms":witness_ms,"refutation_cells":witness_cells}
            fixture_records.append(record); fixture_certs.append((req,cert))
            timing.extend([{"population":"fixture","id":req["id"],"method":"produce","milliseconds":produce_ns/1e6},
                           {"population":"fixture","id":req["id"],"method":"proof-check","milliseconds":check_ns/1e6},
                           {"population":"fixture","id":req["id"],"method":"topological-direct","milliseconds":topological_ns/1e6},
                           {"population":"fixture","id":req["id"],"method":"session-direct-result","milliseconds":session_ns/1e6}])
            if witness_ms is not None:
                timing.append({"population":"fixture","id":req["id"],"method":"one-point-refutation","milliseconds":witness_ms})
            if variant=="correct":
                proof_ops_correct.update(proof_counts); topological_ops_correct.update(topo_counts)
                counts,tick=counter(); t0=time.perf_counter_ns(); rebuilt=proof_check(req,cert,tick,mode="rebuild"); rebuild_ns=time.perf_counter_ns()-t0
                assert rebuilt["status"]=="ACCEPT"; rebuild_outer_ops["proof_cells"] += counts["proof_cells"]
                rebuild_internal_ops["rebuild_cells"] += counts["rebuild_cells"]
                record["certificate_rebuild_ms"]=rebuild_ns/1e6
                timing.append({"population":"fixture","id":req["id"],"method":"certificate-rebuild","milliseconds":rebuild_ns/1e6})
    # Ten repeat timing block over all twenty correct fixtures.
    repeat_rows=[]
    for repeat in range(10):
        for req,cert in [x for x in fixture_certs if x[0]["id"].endswith("-correct")]:
            t0=time.perf_counter_ns(); proof_check(req,cert); elapsed=(time.perf_counter_ns()-t0)/1e6
            repeat_rows.append({"repeat":repeat,"id":req["id"],"method":"proof-check","milliseconds":elapsed})
            t0=time.perf_counter_ns(); evaluate_topological(req); elapsed=(time.perf_counter_ns()-t0)/1e6
            repeat_rows.append({"repeat":repeat,"id":req["id"],"method":"topological-direct","milliseconds":elapsed})
            t0=time.perf_counter_ns(); direct_result(req); elapsed=(time.perf_counter_ns()-t0)/1e6
            repeat_rows.append({"repeat":repeat,"id":req["id"],"method":"session-direct-result","milliseconds":elapsed})
            t0=time.perf_counter_ns(); proof_check(req,cert,mode="rebuild"); elapsed=(time.perf_counter_ns()-t0)/1e6
            repeat_rows.append({"repeat":repeat,"id":req["id"],"method":"certificate-rebuild","milliseconds":elapsed})
    # 6,000 targeted rejection attempts: 20 fixtures x 10 seeds x 30 mutation classes.
    # All but the stale-digest class are rehashed, so deeper checks are exercised.
    controls=[]; kinds=(
        "vector","topology-op","topology-child",
        "source-original","source-candidate","source-reference","source-repair_guard",
        "root-defined","root-repair","root-preserve","guard-root",
        "role-output","role-defined","trace-site","trace-reachable","trace-guard",
        "vector-length","vector-type","node-sort","node-id","node-data",
        "node-extra-field","node-missing-field","node-count",
        "point-order","point-value","domain-binding","request-id",
        "extra-top-field","certificate-digest")
    for req,cert in [x for x in fixture_certs if x[0]["id"].endswith("-correct")]:
        for repeat in range(10):
            for kind in kinds:
                damaged=mutate(cert,kind,repeat*97+int(req["id"].split("-")[1]))
                try:
                    proof_check(req,damaged); status="MISSED"; reason="accepted"
                except (Invalid,Unsupported) as exc:
                    status="REJECTED"; reason=str(exc)
                controls.append({"id":req["id"],"repeat":repeat,"mutation":kind,"status":status,"reason":reason})
                if repeat==0: save(out/"controls"/(req["id"]+"-"+kind+".json"),damaged)
    assert len(controls)==6000 and all(r["status"]=="REJECTED" for r in controls)
    # Three hundred deterministic stress requests, generated independently of Codeflaws.
    for index in range(300):
        req,rows=stress_request(index); expected=oracle_witness(rows)
        save_request(out/"stress-inputs"/(req["id"]+".json"),req)
        t0=time.perf_counter_ns(); cert=produce(req); produce_ns=time.perf_counter_ns()-t0
        save(out/"stress-certificates"/(req["id"]+".json"),cert)
        proof_counts,tick=counter(); t0=time.perf_counter_ns(); got=proof_check(req,cert,tick); check_ns=time.perf_counter_ns()-t0
        proof_ops_all.update(proof_counts)
        t0=time.perf_counter_ns(); topological=evaluate_topological(req); topological_ns=time.perf_counter_ns()-t0
        t0=time.perf_counter_ns(); session_direct=direct_result(req); session_ns=time.perf_counter_ns()-t0
        assert got["witness"]==expected and topological["witness"]==expected and session_direct["witness"]==expected
        assert got["status"]==topological["status"]==session_direct["status"]
        witness_bytes=None; witness_ms=None; witness_cells=None
        if got["status"]=="REFUTED":
            witness_cert=produce_refutation(req,got["witness"]); save(out/"refutation-witnesses"/(req["id"]+".json"),witness_cert)
            witness_counts,tick=counter(); t0=time.perf_counter_ns(); witness_result=refutation_check(req,witness_cert,tick); witness_ns=time.perf_counter_ns()-t0
            assert witness_result["witness"]==got["witness"]
            witness_bytes=len(canonical_bytes(witness_cert)); witness_ms=witness_ns/1e6; witness_cells=witness_counts["refutation_cells"]
            refutation_records.append({"id":req["id"],"population":"stress","certificate_bytes":witness_bytes,"full_certificate_bytes":len(canonical_bytes(cert)),
                "check_ms":witness_ms,"checked_cells":witness_cells,"full_proof_cells":got["checked_cells"]})
            refutation_certificates.append((req,witness_cert))
        else:
            first_point=[req["inputs"][name][0] for name in req["inputs"]]
            fake=produce_refutation(req,{"obligation":OBLIGATIONS[0],"input":first_point,"trace":[]})
            try:
                refutation_check(req,fake); misuse_status="MISSED"; misuse_reason="accepted"
            except (Invalid,Unsupported) as exc:
                misuse_status="REJECTED"; misuse_reason=str(exc)
            acceptance_misuse_controls.append({"id":req["id"],"status":misuse_status,"reason":misuse_reason})
        stress_records.append({"id":req["id"],"variant":VARIANTS[index%4],"status":got["status"],"witness":got["witness"],
                               "nodes":len(cert["nodes"]),"points":len(cert["points"]),"certificate_bytes":len(canonical_bytes(cert)),
                               "produce_ms":produce_ns/1e6,"check_ms":check_ns/1e6,"topological_ms":topological_ns/1e6,
                               "session_direct_ms":session_ns/1e6,"refutation_certificate_bytes":witness_bytes,
                               "refutation_check_ms":witness_ms,"refutation_cells":witness_cells})
        timing.extend([{"population":"stress","id":req["id"],"method":"produce","milliseconds":produce_ns/1e6},
                       {"population":"stress","id":req["id"],"method":"proof-check","milliseconds":check_ns/1e6},
                       {"population":"stress","id":req["id"],"method":"topological-direct","milliseconds":topological_ns/1e6},
                       {"population":"stress","id":req["id"],"method":"session-direct-result","milliseconds":session_ns/1e6}])
        if witness_ms is not None:
            timing.append({"population":"stress","id":req["id"],"method":"one-point-refutation","milliseconds":witness_ms})
    assert len(refutation_certificates)==285
    refutation_control_kinds=("input-bool","input-outside","obligation","trace-type","trace-content",
                              "source-binding","domain-binding","request-id","extra-field","digest")
    refutation_controls=[]
    for cert_index,(req,witness_cert) in enumerate(refutation_certificates):
        for kind in refutation_control_kinds:
            damaged=mutate_refutation(witness_cert,kind)
            try:
                refutation_check(req,damaged); status="MISSED"; reason="accepted"
            except (Invalid,Unsupported) as exc:
                status="REJECTED"; reason=str(exc)
            refutation_controls.append({"id":req["id"],"mutation":kind,"status":status,"reason":reason})
            if cert_index<20:
                save(out/"refutation-controls"/(req["id"]+"-"+kind+".json"),damaged)
    assert len(refutation_controls)==2850 and all(r["status"]=="REJECTED" for r in refutation_controls)
    assert len(acceptance_misuse_controls)==95 and all(r["status"]=="REJECTED" for r in acceptance_misuse_controls)
    all_records=fixture_records+stress_records
    proof_cells_correct=proof_ops_correct["proof_cells"]
    topological_cells_correct=topological_ops_correct["topological_cells"]
    rebuild_outer_cells_correct=rebuild_outer_ops["proof_cells"]
    rebuild_internal_cells_correct=rebuild_internal_ops["rebuild_cells"]
    assert proof_cells_correct==topological_cells_correct
    deterministic_witness_index=[{k:r[k] for k in ("id","population","full_certificate_bytes","certificate_bytes","checked_cells","full_proof_cells")} for r in refutation_records]
    result_index=[{k:r[k] for k in ("id","status","witness","nodes","points","certificate_bytes")} for r in all_records]
    witness_index_sha256=hashlib.sha256(canonical_bytes(deterministic_witness_index)).hexdigest()
    refutation_control_index_sha256=hashlib.sha256(canonical_bytes(refutation_controls)).hexdigest()
    acceptance_misuse_sha256=hashlib.sha256(canonical_bytes(acceptance_misuse_controls)).hexdigest()
    result_index_sha256=hashlib.sha256(canonical_bytes(result_index)).hexdigest()
    def stats(field,records=all_records):
        v=[r[field] for r in records if r.get(field) is not None]
        return {"median":statistics.median(v),"p25":percentile(v,.25),"p75":percentile(v,.75),"min":min(v),"max":max(v)}
    repeat_by=defaultdict(list)
    for row in repeat_rows: repeat_by[row["method"]].append(row["milliseconds"])
    summary={
      "schema":"structured-study-v2","outcome":"PASS","generated_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "fixture_requests":80,"fixture_families":20,"stress_requests":300,"total_requests":380,
      "accepted":sum(r["status"]=="ACCEPT" for r in all_records),"refuted":sum(r["status"]=="REFUTED" for r in all_records),
      "oracle_agreements":len(all_records),"oracle_disagreements":0,
      "tamper_attempts":len(controls),"tamper_rejections":sum(r["status"]=="REJECTED" for r in controls),
      "refutation_witnesses":len(refutation_records),"refutation_witness_agreements":len(refutation_records),
      "refutation_tamper_attempts":len(refutation_controls),
      "refutation_tamper_rejections":sum(r["status"]=="REJECTED" for r in refutation_controls),
      "acceptance_misuse_attempts":len(acceptance_misuse_controls),
      "acceptance_misuse_rejections":sum(r["status"]=="REJECTED" for r in acceptance_misuse_controls),
      "timing_ms":{"produce":stats("produce_ms"),"proof_check":stats("check_ms"),
                   "topological_direct":stats("topological_ms"),"session_direct_result":stats("session_direct_ms"),
                   "certificate_rebuild_correct":stats("certificate_rebuild_ms",[r for r in fixture_records if r.get("certificate_rebuild_ms") is not None]),
                   "one_point_refutation":stats("check_ms",refutation_records),
                   "repeated_correct":{"proof_check":{"median":statistics.median(repeat_by["proof-check"]),"p25":percentile(repeat_by["proof-check"],.25),"p75":percentile(repeat_by["proof-check"],.75)},
                                       "topological_direct":{"median":statistics.median(repeat_by["topological-direct"]),"p25":percentile(repeat_by["topological-direct"],.25),"p75":percentile(repeat_by["topological-direct"],.75)},
                                       "session_direct_result":{"median":statistics.median(repeat_by["session-direct-result"]),"p25":percentile(repeat_by["session-direct-result"],.25),"p75":percentile(repeat_by["session-direct-result"],.75)},
                                       "certificate_rebuild":{"median":statistics.median(repeat_by["certificate-rebuild"]),"p25":percentile(repeat_by["certificate-rebuild"],.25),"p75":percentile(repeat_by["certificate-rebuild"],.75)}}},
      "certificate_bytes":stats("certificate_bytes"),"node_count":stats("nodes"),
      "refutation_certificate_bytes":stats("certificate_bytes",refutation_records),
      "refutation_full_certificate_bytes":stats("full_certificate_bytes",refutation_records),
      "refutation_encoding":{"same_population":len(refutation_records),
                              "median_full_bytes":statistics.median(r["full_certificate_bytes"] for r in refutation_records),
                              "median_compact_bytes":statistics.median(r["certificate_bytes"] for r in refutation_records),
                              "ratio_of_medians":statistics.median(r["full_certificate_bytes"] for r in refutation_records)/statistics.median(r["certificate_bytes"] for r in refutation_records),
                              "median_paired_ratio":statistics.median(r["full_certificate_bytes"]/r["certificate_bytes"] for r in refutation_records)},
      "refutation_checked_cells":stats("checked_cells",refutation_records),
      "refutation_full_proof_cells":stats("full_proof_cells",refutation_records),
      "proof_operation_counts_all":dict(proof_ops_all),
      "proof_operation_counts_correct":dict(proof_ops_correct),
      "topological_operation_counts_correct":dict(topological_ops_correct),
      "proof_operation_counts_all_scope":"all 380 frozen-core requests",
      "certificate_rebuild_operation_counts_correct":{"outer_proof_cells":rebuild_outer_cells_correct,
                                                        "internal_recursive_cells":rebuild_internal_cells_correct},
      "work_equivalence":{"proof_cells_correct":proof_cells_correct,
                          "topological_direct_cells_correct":topological_cells_correct,
                          "exact_equal":proof_cells_correct==topological_cells_correct,
                          "certificate_rebuild_outer_cells_correct":rebuild_outer_cells_correct,
                          "certificate_rebuild_internal_recursive_cells_correct":rebuild_internal_cells_correct,
                          "internal_recursive_over_proof_ratio":rebuild_internal_cells_correct/proof_cells_correct},
      "refutation_work":{"median_cell_reduction_factor":statistics.median(r["full_proof_cells"]/r["checked_cells"] for r in refutation_records),
                         "all_one_point":all(r["full_proof_cells"]//r["checked_cells"]==81 for r in refutation_records)},
      "deterministic_indexes":{"results_sha256":result_index_sha256,
                               "refutation_witnesses_sha256":witness_index_sha256,
                               "refutation_controls_sha256":refutation_control_index_sha256,
                               "acceptance_misuse_sha256":acceptance_misuse_sha256},
      "peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      "scope":"20 designed C-fragment fixture families plus 300 deterministic generated stress requests; stress requests are not Codeflaws."
    }
    save(out/"structured-study.json",summary); save(out/"fixture-cases.json",fixture_records); save(out/"stress-cases.json",stress_records); save(out/"tamper-controls.json",controls); save(out/"timing-repeats.json",repeat_rows)
    save(out/"refutation-witnesses.json",refutation_records); save(out/"refutation-controls.json",refutation_controls); save(out/"acceptance-misuse-controls.json",acceptance_misuse_controls); save(out/"timing-all.json",timing)
    for name,records in (("fixture-cases.csv",fixture_records),("stress-cases.csv",stress_records),("tamper-controls.csv",controls),("timing-repeats.csv",repeat_rows),("refutation-witnesses.csv",refutation_records),("refutation-controls.csv",refutation_controls),("acceptance-misuse-controls.csv",acceptance_misuse_controls),("timing-all.csv",timing)):
        with (out/name).open("w",newline="") as handle:
            fields=list(records[0]); writer=csv.DictWriter(handle,fieldnames=fields,extrasaction="ignore"); writer.writeheader(); writer.writerows(records)
    print(json.dumps(summary,indent=2,sort_keys=True))

if __name__=="__main__": main()
