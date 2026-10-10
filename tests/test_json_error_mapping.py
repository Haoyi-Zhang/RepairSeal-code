"""Small local JSON tests; resource exceptions are mocked, never induced."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import proof_dag_checker as full
import refutation_witness_checker as compact


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


if __name__ == "__main__":
    unittest.main()
