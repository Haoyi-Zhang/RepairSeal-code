"""Small local JSON tests; resource exceptions are mocked, never induced."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import proof_dag_checker as full
import refutation_witness_checker as compact
from reproduce_all_core import compare_security_evidence


class JsonErrorMappingTests(unittest.TestCase):
    def test_ordinary_record_keeps_canonical_bytes_and_decodes(self):
        record = {"value": 3, "ok": True}
        self.assertEqual(full.canonical_bytes(record), b'{"ok":true,"value":3}')
        self.assertEqual(full.load_json_strict('{"value":3,"ok":true}'), record)

    def test_mock_decoder_failures_are_invalid(self):
        for error in (ValueError, TypeError, UnicodeError, OverflowError,
                      RecursionError, MemoryError):
            with self.subTest(error=error.__name__), patch.object(
                    full.json, "loads", side_effect=error("mock failure")):
                with self.assertRaisesRegex(full.Invalid, "JSON decoding"):
                    full.load_json_strict('{"value":3}')

    def test_mock_syntax_exception_has_the_current_diagnostic(self):
        error = json.JSONDecodeError("mock syntax failure", "", 0)
        with patch.object(full.json, "loads", side_effect=error):
            with self.assertRaisesRegex(full.Invalid, "^JSON decoding$") as caught:
                full.load_json_strict('{"value":3}')
        self.assertIs(caught.exception.__cause__, error)

    def test_mock_encoder_failures_are_invalid(self):
        for error in (ValueError, TypeError, UnicodeError, OverflowError,
                      RecursionError, MemoryError):
            with self.subTest(error=error.__name__), patch.object(
                    full.json, "dumps", side_effect=error("mock failure")):
                with self.assertRaisesRegex(full.Invalid, "JSON canonical encoding"):
                    full.canonical_bytes({"value": 3})

    def test_both_cli_handlers_report_normalized_failures(self):
        for module in (full, compact):
            for stage in ("decode", "encode"):
                output = io.StringIO()
                load_patch = patch.object(module, "load_json_strict", return_value={})
                check_patch = patch.object(module, "check")
                with self.subTest(module=module.__name__, stage=stage), \
                        patch.object(sys, "argv", ["checker", "request.json", "certificate.json"]), \
                        patch.object(Path, "read_text", return_value='{"value":3}'), \
                        load_patch as load, check_patch as check, \
                        contextlib.redirect_stdout(output):
                    if stage == "decode":
                        load.side_effect = full.Invalid("JSON decoding")
                    else:
                        check.side_effect = full.Invalid("JSON canonical encoding")
                    module.main()
                result = json.loads(output.getvalue())
                self.assertEqual(result["status"], "INVALID")
                self.assertIn("JSON", result["reason"])


class SecurityComparisonTests(unittest.TestCase):
    """Receipt-only comparisons: no generator, security controls or campaigns."""

    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "proof-data/security-regression.json"
        self.retained = json.loads(path.read_text(encoding="utf-8"))
        self.current = copy.deepcopy(self.retained)
        row = next(row for row in self.current["json_text_rejections"]
                   if row["case"] == "malformed-json")
        self.assertEqual(row["reason"], "JSON syntax")
        row["reason"] = "JSON decoding"

    def test_only_known_label_transition_passes_without_mutation(self):
        before = copy.deepcopy((self.retained, self.current))
        compare_security_evidence(self.retained, self.current)
        compare_security_evidence(self.current, self.current)
        self.assertEqual((self.retained, self.current), before)

    def test_current_receipt_must_use_current_diagnostic(self):
        with self.assertRaises(AssertionError):
            compare_security_evidence(self.retained, self.retained)

    def test_other_rejection_reasons_remain_strict(self):
        for section in ("json_text_rejections", "request_rejections", "certificate_type_rejections"):
            for index, row in enumerate(self.current[section]):
                if row["case"] == "malformed-json":
                    continue
                with self.subTest(section=section, case=row["case"]):
                    wrong = copy.deepcopy(self.current)
                    wrong[section][index]["reason"] = "other diagnostic"
                    with self.assertRaises(AssertionError):
                        compare_security_evidence(self.retained, wrong)

    def test_counts_status_shape_and_import_boundary_remain_strict(self):
        mutations = (
            lambda value: value.update(request_rejection_cases=46),
            lambda value: value.update(json_text_rejection_cases=4.0),
            lambda value: value.update(acceptance_boundary_cases=True),
            lambda value: value.update(outcome="FAIL"),
            lambda value: value.update(schema="other-schema"),
            lambda value: value["json_text_rejections"][-1].update(status="ACCEPT"),
            lambda value: value["json_text_rejections"].pop(),
            lambda value: value["json_text_rejections"].reverse(),
            lambda value: value["operator_probe_records"][0].update(nodes=0),
            lambda value: value["operator_coverage"].pop(),
            lambda value: value["import_boundary"]["imports"].append("producer"),
            lambda value: value.update(unexpected=True),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                wrong = copy.deepcopy(self.current)
                mutate(wrong)
                with self.assertRaises(AssertionError):
                    compare_security_evidence(self.retained, wrong)


if __name__ == "__main__":
    unittest.main()
