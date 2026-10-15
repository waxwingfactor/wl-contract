"""Historical upstream regression and multi-interface contract scenarios."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RevisionIntegrationTests(unittest.TestCase):
    def run_pair(self, before, after, expected):
        with tempfile.TemporaryDirectory(prefix="wl-contract-integration-") as folder:
            base = Path(folder)
            (base / "old.xml").write_text(before, encoding="utf-8")
            (base / "new.xml").write_text(after, encoding="utf-8")
            env = os.environ.copy()
            if env.get("WL_CONTRACT_TEST_INSTALLED") == "1":
                env.pop("PYTHONPATH", None)
            else:
                env["PYTHONPATH"] = str(ROOT / "src")
            env["PYTHONNOUSERSITE"] = "1"
            result = subprocess.run([sys.executable, "-m", "wl_contract", "compare",
                                     str(base / "old.xml"), str(base / "new.xml"), "--format", "json"],
                                    cwd=base, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            return json.loads(result.stdout)

    def test_actual_upstream_blur_correction_is_one_numeric_break(self):
        fixtures = ROOT / "tests/fixtures/upstream"
        report = self.run_pair((fixtures / "ext-background-effect.before.xml").read_text(encoding="utf-8"),
                               (fixtures / "ext-background-effect.after.xml").read_text(encoding="utf-8"), 1)
        self.assertEqual(len(report["findings"]), 1)
        finding = report["findings"][0]
        self.assertEqual((finding["code"], finding["old"], finding["new"]),
                         ("enum_value_changed", 0, 1))

    def family(self, parent_version, child_version, extra=""):
        return ('<protocol name="family"><interface name="parent_v1" version="{}">'
                '<request name="create"><arg name="id" type="new_id" interface="child_v1"/></request>'
                '</interface><interface name="child_v1" version="{}">'
                '<request name="destroy" type="destructor"/>{}</interface></protocol>').format(
                    parent_version, child_version, extra)

    def test_parent_increase_must_reach_changed_child_version(self):
        report = self.run_pair(self.family(1, 1), self.family(2, 3, '<request name="set" since="3"/>'), 1)
        self.assertIn("constructor_version_not_propagated", [f["code"] for f in report["findings"]])

    def test_parent_propagated_version_has_review_only(self):
        report = self.run_pair(self.family(1, 1), self.family(3, 3, '<request name="set" since="3"/>'), 3)
        self.assertFalse(any(f["severity"] == "break" for f in report["findings"]))

    def simple(self, body, version=1):
        return '<protocol name="example"><interface name="example_v1" version="{}">{}</interface></protocol>'.format(version, body)

    def test_same_wire_rename_requires_api_review(self):
        report = self.run_pair(self.simple('<request name="set"/>'), self.simple('<request name="update"/>'), 3)
        self.assertEqual(report["findings"][0]["severity"], "review")

    def test_version_bump_alone_retains_structural_no_hazards(self):
        self.run_pair(self.simple('<request name="set"/>'), self.simple('<request name="set"/>', 2), 0)

    def test_existing_deprecated_message_cannot_disappear(self):
        before = self.simple('<request name="old" deprecated-since="2"/><request name="current"/>', 2)
        after = self.simple('<request name="current"/>', 2)
        self.run_pair(before, after, 1)

    def test_existing_enum_member_cannot_disappear(self):
        base = '<request name="set"/><enum name="states">{}</enum>'
        before = self.simple(base.format('<entry name="one" value="1"/><entry name="two" value="2"/>'))
        after = self.simple(base.format('<entry name="one" value="1"/>'))
        self.run_pair(before, after, 1)

    def test_enum_member_order_is_numeric_not_positional(self):
        first, second = '<entry name="one" value="1"/>', '<entry name="two" value="2"/>'
        template = '<request name="set"/><enum name="states">{}</enum>'
        self.run_pair(self.simple(template.format(first + second)), self.simple(template.format(second + first)), 0)

    def test_prose_whitespace_change_is_neutral(self):
        before = self.simple('<description summary="state">Apply on\n commit.</description><request name="set"/>')
        self.run_pair(before, before.replace('on\n commit', 'on commit'), 0)


if __name__ == "__main__":
    unittest.main()
