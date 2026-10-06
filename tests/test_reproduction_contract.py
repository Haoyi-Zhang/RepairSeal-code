"""Portable regressions for scientific comparison and non-destructive output.

Compiler variations below are explicitly synthetic comparison fixtures, not
new compiler executions or replacement provenance. No C program is run here.
Set P004_TEST_TMP to isolate all temporary fixtures from the artifact tree.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import release_gate
from scientific_comparison import compare_evidence, scientific_view

NATIVE_FILES = ("study.json", "native-compilers.json", "native-harness.c",
                "native-outputs-gcc.csv", "native-outputs-clang.csv")


def environment_variant(obj, name):
    changed = copy.deepcopy(obj)
    native = changed["native"] if name == "study.json" else changed
    for compiler in native["compilers"]:
        compiler["executable"] = "/synthetic/other-toolchain/" + compiler["id"]
        compiler["version_first_line"] = compiler["id"] + " synthetic comparison-only version"
        for field in ("version_command", "compile_command"):
            compiler[field][0] = compiler["executable"]
    return changed


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="p004-comparison-", dir=os.environ.get("P004_TEST_TMP"))
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.before = self.base / "retained"
        self.after = self.base / "synthetic-environment"
        self.before.mkdir(); self.after.mkdir()
        for name in NATIVE_FILES:
            raw = (ROOT / "results" / name).read_bytes()
            (self.before / name).write_bytes(raw)
            (self.after / name).write_bytes(raw)
        for name in NATIVE_FILES[:2]:
            obj = json.loads((self.after / name).read_text(encoding="utf-8"))
            self.save(name, environment_variant(obj, name))

    def save(self, name, obj):
        (self.after / name).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")

    def compare(self, name):
        compare_evidence(self.before / name, self.after / name, name)

    def test_environment_only_allowed_without_rewriting_provenance(self):
        snapshots = {str(path): path.read_bytes() for directory in (self.before, self.after) for path in directory.iterdir()}
        for name in NATIVE_FILES:
            self.compare(name)
        for path, raw in snapshots.items():
            self.assertEqual(Path(path).read_bytes(), raw)
        for name in NATIVE_FILES[:2]:
            self.assertNotEqual((self.before / name).read_bytes(), (self.after / name).read_bytes())

    def test_one_wrong_observed_output_rejected_for_each_frontend(self):
        for name in NATIVE_FILES[3:]:
            with self.subTest(name=name):
                path = self.after / name
                raw = path.read_bytes()
                lines = raw.splitlines(keepends=True)
                fields = lines[1].decode("ascii").strip().split(",")
                fields[-1] = str(int(fields[-1]) ^ 1)
                lines[1] = (",".join(fields) + "\r\n").encode("ascii")
                path.write_bytes(b"".join(lines))
                with self.assertRaisesRegex(AssertionError, "evidence bytes differ"):
                    self.compare(name)
                path.write_bytes(raw)

    def test_expected_output_and_harness_changes_rejected(self):
        for name in NATIVE_FILES[2:]:
            with self.subTest(name=name):
                path = self.after / name
                raw = path.read_bytes()
                if name.endswith(".csv"):
                    lines = raw.splitlines(keepends=True)
                    fields = lines[1].decode("ascii").strip().split(",")
                    fields[-2] = str(int(fields[-2]) ^ 1)
                    lines[1] = (",".join(fields) + "\r\n").encode("ascii")
                    path.write_bytes(b"".join(lines))
                else:
                    path.write_bytes(raw + b"/* comparison-only source change */\n")
                with self.assertRaises(AssertionError):
                    self.compare(name)
                path.write_bytes(raw)

    def test_compiler_protocol_changes_rejected_in_both_records(self):
        mutations = {
            "frontend-role": lambda c: c.update(id="other"),
            "compile-returncode": lambda c: c.update(compile_returncode=1),
            "run-returncode": lambda c: c.update(run_returncode=1),
            "returncode-type": lambda c: c.update(run_returncode=False),
            "language-standard": lambda c: c["compile_command"].__setitem__(1, "-std=c99"),
            "optimization": lambda c: c["compile_command"].__setitem__(2, "-O2"),
            "extra-option": lambda c: c["compile_command"].append("-DNDEBUG"),
            "source-argument": lambda c: c["compile_command"].__setitem__(3, "other.c"),
            "output-argument": lambda c: c["compile_command"].__setitem__(5, "other-binary"),
            "version-argument": lambda c: c["version_command"].append("--verbose"),
            "run-command": lambda c: c.update(run_command=["./other-binary"]),
            "output-file": lambda c: c.update(output_file="other.csv"),
            "command-executable": lambda c: c["compile_command"].__setitem__(0, "/inconsistent/compiler"),
            "missing-version": lambda c: c.pop("version_first_line"),
            "extra-field": lambda c: c.update(unexpected=1),
        }
        for name in NATIVE_FILES[:2]:
            original = json.loads((self.after / name).read_text(encoding="utf-8"))
            for frontend in range(2):
                for label, mutate in mutations.items():
                    with self.subTest(record=name, frontend=frontend, mutation=label):
                        changed = copy.deepcopy(original)
                        native = changed["native"] if name == "study.json" else changed
                        mutate(native["compilers"][frontend]); self.save(name, changed)
                        with self.assertRaises((AssertionError, KeyError)):
                            self.compare(name)
            self.save(name, original)

    def test_counts_and_scientific_summary_changes_rejected(self):
        for name in NATIVE_FILES[:2]:
            original = json.loads((self.after / name).read_text(encoding="utf-8"))
            native = original["native"] if name == "study.json" else original
            fields = ("unique_functions", "unique_defined_evaluations", "undefined_candidate_observations_excluded",
                      "return_value_disagreements", "compiler_count", "cross_compiler_disagreements") if name == "study.json" else ("rows_per_compiler", "cross_compiler_disagreements")
            for field in fields:
                with self.subTest(record=name, field=field):
                    changed = copy.deepcopy(original)
                    target = changed["native"] if name == "study.json" else changed
                    target[field] = native[field] + 1; self.save(name, changed)
                    with self.assertRaises(AssertionError): self.compare(name)
            for label in ("missing-frontend", "frontend-order", "protocol"):
                with self.subTest(record=name, field=label):
                    changed = copy.deepcopy(original)
                    target = changed["native"] if name == "study.json" else changed
                    if label == "missing-frontend": target["compilers"].pop()
                    elif label == "frontend-order": target["compilers"].reverse()
                    elif name == "study.json": target["compile_options"] = ["-std=c11", "-O2"]
                    else: target["harness"] = "other.c"
                    self.save(name, changed)
                    with self.assertRaises(AssertionError): self.compare(name)
            self.save(name, original)

    def test_no_global_provenance_or_hash_filter(self):
        obj = {"executable": "/real/program", "version_first_line": "v1", "compile_command": ["/real/program", "-O0"],
               "source_sha256": "a" * 64, "nested": {"resources": {"cells": 42}}}
        self.assertEqual(scientific_view(obj, "certificates/study.json"), obj)
        for field in obj:
            changed = copy.deepcopy(obj); changed[field] = "changed"
            self.assertNotEqual(scientific_view(obj, "certificate.json"), scientific_view(changed, "certificate.json"))

    def test_top_level_resource_measurements_still_excluded(self):
        self.assertEqual(scientific_view({"cells": 42, "resources": {"wall_seconds": 1}}, "report.json"),
                         scientific_view({"cells": 42, "resources": {"wall_seconds": 2}}, "report.json"))

    def test_counted_work_remains_scientific_evidence(self):
        obj = {"resources": {"counts": {"proof_cells": 42}, "work_events": 42, "workers": 1,
                             "wall_seconds": 0.1, "self_peak_rss_kib": 100}}
        changed = copy.deepcopy(obj)
        changed["resources"].update(wall_seconds=1.2, self_peak_rss_kib=200)
        self.assertEqual(scientific_view(obj, "report.json"), scientific_view(changed, "report.json"))
        for field in ("counts", "work_events", "workers"):
            with self.subTest(field=field):
                wrong = copy.deepcopy(obj)
                wrong["resources"][field] = {"proof_cells": 43} if field == "counts" else 43
                self.assertNotEqual(scientific_view(obj, "report.json"), scientific_view(wrong, "report.json"))


class OutputSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="p004-output-safety-", dir=os.environ.get("P004_TEST_TMP"))
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def test_nonempty_directory_preserved(self):
        target = self.base / "occupied"; target.mkdir()
        sentinel = target / "keep.txt"; sentinel.write_bytes(b"user-owned evidence")
        with self.assertRaisesRegex(SystemExit, "existing output is preserved"):
            with release_gate.reproduction_output(target): self.fail("nonempty target admitted")
        self.assertEqual(sentinel.read_bytes(), b"user-owned evidence")

    def test_nested_directory_alone_is_nonempty(self):
        target = self.base / "occupied"; (target / "child").mkdir(parents=True)
        with self.assertRaises(SystemExit):
            with release_gate.reproduction_output(target): self.fail("nonempty target admitted")
        self.assertTrue((target / "child").is_dir())

    def test_file_target_preserved(self):
        target = self.base / "file"; target.write_bytes(b"do not delete")
        with self.assertRaises(SystemExit):
            with release_gate.reproduction_output(target): self.fail("file target admitted")
        self.assertEqual(target.read_bytes(), b"do not delete")

    def test_new_and_empty_user_outputs_work_and_are_retained(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                target = self.base / str(existing) / "output"
                if existing: target.mkdir(parents=True)
                with release_gate.reproduction_output(target) as out:
                    self.assertEqual(out, target.resolve())
                    out.mkdir(exist_ok=True); (out / "fixture.txt").write_bytes(b"benign lifecycle fixture")
                self.assertEqual((target / "fixture.txt").read_bytes(), b"benign lifecycle fixture")

    def test_user_output_retained_on_failure(self):
        target = self.base / "failure"
        with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
            with release_gate.reproduction_output(target) as out:
                out.mkdir(); (out / "partial.txt").write_bytes(b"diagnostic")
                raise RuntimeError("synthetic failure")
        self.assertEqual((target / "partial.txt").read_bytes(), b"diagnostic")

    def test_owned_temporary_output_works_and_cleans_up(self):
        with mock.patch.object(tempfile, "tempdir", str(self.base)):
            with release_gate.reproduction_output(None) as out:
                self.assertTrue(out.is_relative_to(self.base))
                self.assertFalse(out.exists())
                out.mkdir(); (out / "fixture.txt").write_bytes(b"benign lifecycle fixture")
                parent = out.parent
            self.assertFalse(parent.exists())

    def test_owned_temporary_output_cleans_up_on_failure(self):
        with mock.patch.object(tempfile, "tempdir", str(self.base)):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                with release_gate.reproduction_output(None) as out:
                    parent = out.parent; out.mkdir()
                    raise RuntimeError("synthetic failure")
            self.assertFalse(parent.exists())

    def test_gate_refuses_nonempty_output_before_launching_reproducer(self):
        target = self.base / "occupied"; target.mkdir()
        sentinel = target / "keep.txt"; sentinel.write_bytes(b"retained")
        with mock.patch.object(sys, "argv", ["release_gate.py", "--keep-output", str(target)]), \
             mock.patch.object(release_gate.subprocess, "run") as run:
            with self.assertRaisesRegex(SystemExit, "existing output is preserved"):
                release_gate.main()
            run.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b"retained")


if __name__ == "__main__":
    unittest.main(verbosity=2)
