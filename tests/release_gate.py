#!/usr/bin/env python3
"""Functional release gate for a clean standalone artifact tree.

This deliberately checks dependency closure by running the public reproducer;
it does not rely on a generated checksum or inventory manifest.
"""
from __future__ import annotations
import argparse, ast, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md", "LICENSE", "claim_evidence_ledger.csv", "formats.md",
    "public-data/codeflaws-first-300.tsv",
    "proof-data/structured-study.json", "proof-data/security-regression.json",
    "proof-data/codeflaws-archive-audit.json",
    "proof-data/edge-case-regression.json", "proof-data/disk-replay-audit.json",
    "proof-data/holdout-differential/summary.json",
    "tests/reproduce_all.py", "tests/reproduce_all_core.py",
    "tests/holdout_differential.py", "tests/disk_replay.py", "tests/edge_case_regression.py",
    "src/proof_dag_checker.py", "src/refutation_witness_checker.py",
]
FORBIDDEN_NAMES = {"CHECKSUMS.sha256", "MANIFEST.json"}
FORBIDDEN_SUFFIXES = {".zip", ".tar", ".gz", ".bz2", ".xz", ".pyc"}

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep-output", type=Path)
    args = ap.parse_args()
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit("missing required files: " + ", ".join(missing))
    forbidden = []
    for path in ROOT.rglob("*"):
        if "__pycache__" in path.parts or path.name in FORBIDDEN_NAMES or path.suffix in FORBIDDEN_SUFFIXES:
            forbidden.append(str(path.relative_to(ROOT)))
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if forbidden:
        raise SystemExit("forbidden packaged files: " + ", ".join(sorted(forbidden)[:20]))
    if args.keep_output:
        out = args.keep_output.resolve()
        if out.exists():
            shutil.rmtree(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        tmp = tempfile.TemporaryDirectory(prefix="semantic-cert-release-")
        out = Path(tmp.name) / "replayed"
        cleanup = True
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "reproduce_all.py"), "--output", str(out)],
        cwd=ROOT, text=True, capture_output=True,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
    )
    if proc.returncode:
        raise SystemExit(proc.stdout + proc.stderr)
    result = json.loads((out / "complete-reproduction.json").read_text())
    if result.get("outcome") != "PASS_COMPLETE_REPRODUCTION":
        raise SystemExit(json.dumps(result, indent=2))
    report = {
        "outcome": "PASS_FUNCTIONAL_RELEASE_GATE",
        "required_files": len(REQUIRED),
        "python_files_parsed": sum(1 for _ in ROOT.rglob("*.py")),
        "reproduction": result,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if cleanup:
        tmp.cleanup()

if __name__ == "__main__":
    main()
