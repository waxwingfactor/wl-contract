"""Independent review regressions for terminal-safe report publication."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
XML = ('<protocol name="example"><interface name="example_v1" version="1">'
       '<request name="ping"/></interface></protocol>')


@unittest.skipIf(os.name == "nt", "Windows forbids control characters in filenames")
class TerminalReportReviewTests(unittest.TestCase):
    def invoke(self, old_text):
        with tempfile.TemporaryDirectory(prefix="wl-contract-review-") as folder:
            root = Path(folder)
            old = root / "old\x1b[2J.xml"
            new = root / "new.xml"
            old.write_text(old_text, encoding="utf-8")
            new.write_text(XML, encoding="utf-8")
            env = os.environ.copy()
            if env.get("WL_CONTRACT_TEST_INSTALLED") == "1":
                env.pop("PYTHONPATH", None)
            else:
                env["PYTHONPATH"] = str(ROOT / "src")
            env["PYTHONNOUSERSITE"] = "1"
            return subprocess.run(
                [sys.executable, "-m", "wl_contract", "compare", str(old), str(new)],
                cwd=folder, env=env, text=True, capture_output=True, timeout=10,
            )

    def test_text_report_does_not_emit_terminal_controls_from_source_filename(self):
        result = self.invoke(XML)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("\x1b", result.stdout + result.stderr)

    def test_text_error_does_not_emit_terminal_controls_from_source_filename(self):
        result = self.invoke("<protocol>")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertNotIn("\x1b", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
