"""Compare replay evidence without equating compiler identity with its results.

The two on-disk provenance records remain untouched. Only their known native
compiler identity fields are projected for comparison. Compiler roles, every
option/argument after argv[0], return codes, counts and output names remain
scientific evidence. Harness/source and expected/observed CSVs are byte-compared.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

RESOURCE_MEASUREMENTS = {
    "wall_seconds", "self_cpu_seconds", "child_cpu_seconds", "total_cpu_seconds",
    "self_peak_rss_kib", "largest_child_rss_kib",
}


def _compiler_view(record: dict[str, Any]) -> dict[str, Any]:
    view = copy.deepcopy(record)
    executable = view["executable"]
    if not isinstance(executable, str) or not executable:
        raise AssertionError("native compiler executable provenance missing")
    if not isinstance(view["version_first_line"], str) or not view["version_first_line"]:
        raise AssertionError("native compiler version provenance missing")
    for field in ("version_command", "compile_command"):
        command = view[field]
        if not isinstance(command, list) or len(command) < 2 or command[0] != executable:
            raise AssertionError("native command/executable provenance inconsistent: " + field)
        # The generated commands use fixed relative harness/binary names. Only
        # the executable's installation path/version suffix varies by machine;
        # no flags, source/output arguments or command structure are discarded.
        command[0] = "<compiler-executable>"
    view["executable"] = "<compiler-executable>"
    view["version_first_line"] = "<compiler-version>"
    return view


def scientific_view(obj: Any, evidence_name: str) -> Any:
    view = copy.deepcopy(obj)
    if isinstance(view, dict):
        # Omit only the top-level Budget's measured time/RSS fields. Its counted
        # work, category counts and worker count are deterministic and retained.
        # Never recursively filter bindings or nested scientific fields.
        if isinstance(view.get("resources"), dict):
            view["resources"] = {key: value for key, value in view["resources"].items()
                                 if key not in RESOURCE_MEASUREMENTS}
        if evidence_name == "study.json":
            native = view["native"]
        elif evidence_name == "native-compilers.json":
            native = view
        else:
            return view
        native["compilers"] = [_compiler_view(record) for record in native["compilers"]]
    return view


def semantic_json(path: Path, evidence_name: str | None = None) -> Any:
    return scientific_view(json.loads(path.read_text(encoding="utf-8")), evidence_name or path.name)


def compare_evidence(before: Path, after: Path, evidence_name: str) -> None:
    if before.suffix == ".json":
        # Canonical JSON comparison also keeps Booleans distinct from numbers.
        left = json.dumps(semantic_json(before, evidence_name), sort_keys=True, allow_nan=False)
        right = json.dumps(semantic_json(after, evidence_name), sort_keys=True, allow_nan=False)
        if left != right:
            raise AssertionError(("scientific JSON differs", evidence_name))
    elif before.read_bytes() != after.read_bytes():
        raise AssertionError(("evidence bytes differ", evidence_name))
