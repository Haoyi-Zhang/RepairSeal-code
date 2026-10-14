"""Owned driver controls; do not launch campaigns or native compilers."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OptimizedDriverTests(unittest.TestCase):
    def test_direct_core_refuses_optimization_before_output_or_campaign(self):
        with tempfile.TemporaryDirectory(prefix="p004-opt-", dir=os.environ.get("P004_TEST_TMP")) as temporary:
            output = Path(temporary) / "must-not-create"
            program = (
                "import sys; from pathlib import Path; "
                "sys.path.insert(0, str(Path(sys.argv[1]) / 'tests')); "
                "import reproduce_all_core as core; "
                "core.run = lambda command: (_ for _ in ()).throw(RuntimeError('campaign started')); "
                "sys.argv = ['reproduce_all_core.py', '--output', sys.argv[2]]; core.main()"
            )
            result = subprocess.run(
                [sys.executable, "-O", "-c", program, str(ROOT), str(output)],
                capture_output=True, text=True, encoding="utf-8", timeout=15,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires enabled assertions", result.stderr)
            self.assertNotIn("campaign started", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
