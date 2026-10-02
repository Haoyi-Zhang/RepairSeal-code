#!/usr/bin/env python3
"""Run the complete offline reproduction and expose the final audited summary."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    core = Path(__file__).with_name("reproduce_all_core.py")
    proc = subprocess.run(
        [sys.executable, str(core), "--output", str(args.output)],
        text=True,
        capture_output=True,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
    )
    if proc.returncode:
        if proc.stdout:
            print(proc.stdout, end="", file=sys.stderr)
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        raise SystemExit(proc.returncode)
    result_path = args.output / "complete-reproduction.json"
    result = json.loads(result_path.read_text())
    candidates = list(args.output.rglob("structured-study.json"))
    if len(candidates) != 1:
        raise SystemExit(f"expected one structured-study.json, found {len(candidates)}")
    study = json.loads(candidates[0].read_text())
    result.update(
        {
            "structured_requests": study["total_requests"],
            "oracle_agreements": study["oracle_agreements"],
            "full_vector_tamper_controls": study["tamper_attempts"],
            "full_vector_tamper_rejections": study["tamper_rejections"],
            "refutation_witnesses": study["refutation_witnesses"],
            "refutation_witness_agreements": study["refutation_witness_agreements"],
            "refutation_tamper_controls": study["refutation_tamper_attempts"],
            "refutation_tamper_rejections": study["refutation_tamper_rejections"],
            "acceptance_misuse_controls": study["acceptance_misuse_attempts"],
            "acceptance_misuse_rejections": study["acceptance_misuse_rejections"],
            "total_certificate_negative_controls": (
                study["tamper_attempts"]
                + study["refutation_tamper_attempts"]
                + study["acceptance_misuse_attempts"]
            ),
            "full_vector_work_equivalence": study["work_equivalence"],
            "compact_refutation_work": study["refutation_work"],
            "scope_note": (
                "Codeflaws evidence is a pinned archival index audit; public sources "
                "are not executed. Generated stress requests are not Codeflaws."
            ),
        }
    )
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
