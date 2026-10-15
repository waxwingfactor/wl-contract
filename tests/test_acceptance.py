"""Independent black-box acceptance checks for the supported XML contract.

These tests intentionally exercise the public module/JSON/exit-code interface.
They do not import the implementation or mirror its comparison algorithm.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def protocol(body, version=1, description=""):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<protocol name="example">'
        '<interface name="example_factory_v1" version="{}">'
        '{}{}'
        '</interface></protocol>'
    ).format(version, description, body)


FIRST = '<request name="first"><arg name="value" type="uint"/></request>'
SECOND = '<request name="second"><arg name="value" type="uint"/></request>'
TICK = '<event name="tick"><arg name="value" type="uint"/></event>'
DONE = '<event name="done"><arg name="value" type="uint"/></event>'


class ContractAcceptanceTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="wl-contract-acceptance-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.old = self.base / "old.xml"
        self.new = self.base / "new.xml"

    def compare(self, old, new, expected_exit=None):
        self.old.write_text(old, encoding="utf-8")
        self.new.write_text(new, encoding="utf-8")
        return self.run_compare(self.old, self.new, expected_exit)

    def invoke(self, old_path, new_path, extra_args=()):
        env = os.environ.copy()
        if env.get("WL_CONTRACT_TEST_INSTALLED") == "1":
            env.pop("PYTHONPATH", None)
        else:
            env["PYTHONPATH"] = str(ROOT / "src")
        env["PYTHONNOUSERSITE"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "wl_contract", "compare", str(old_path),
             str(new_path), "--format", "json"] + list(extra_args),
            cwd=str(self.base), env=env, text=True, capture_output=True, timeout=15,
        )

    def run_compare(self, old_path, new_path, expected_exit=None):
        result = self.invoke(old_path, new_path)
        if expected_exit is not None:
            self.assertEqual(
                result.returncode, expected_exit,
                "stdout:\n{}\nstderr:\n{}".format(result.stdout, result.stderr),
            )
        if result.returncode == 2:
            self.assertNotIn("Traceback (most recent call last)", result.stderr)
            self.assertTrue(result.stdout.strip() or result.stderr.strip())
            return result, None
        try:
            data = json.loads(result.stdout)
        except ValueError:
            self.fail("CLI did not emit JSON:\n{}\n{}".format(result.stdout, result.stderr))
        self.assertEqual(data["schema_version"], 1)
        self.assertIn(data["verdict"], {
            "no_structural_hazards", "incompatible", "needs_review",
        })
        self.assertIsInstance(data["findings"], list)
        self.assertIsInstance(data["old"]["sources"], list)
        self.assertIsInstance(data["new"]["sources"], list)
        self.assertTrue(data["old"]["sources"])
        self.assertTrue(data["new"]["sources"])
        self.assertIn("limits", data)
        for finding in data["findings"]:
            self.assertIn(finding["severity"], {"break", "review", "info"})
            for key in ("code", "path", "message"):
                self.assertIsInstance(finding[key], str)
                self.assertTrue(finding[key].strip())
            self.assertIn("old", finding)
            self.assertIn("new", finding)
        return result, data

    def assert_break(self, old, new, context=None):
        _, data = self.compare(old, new, 1)
        self.assertEqual(data["verdict"], "incompatible")
        breaking = [f for f in data["findings"] if f["severity"] == "break"]
        self.assertTrue(breaking, (context, data))
        self.assertTrue(any(f["path"].startswith("interface/") for f in breaking), data)
        return data

    def assert_clear(self, old, new):
        _, data = self.compare(old, new, 0)
        self.assertEqual(data["verdict"], "no_structural_hazards")
        self.assertFalse(any(f["severity"] in {"break", "review"}
                             for f in data["findings"]), data)
        return data

    def test_unchanged_contract_is_clear(self):
        xml = protocol(FIRST + SECOND + TICK)
        self.assert_clear(xml, xml)

    def test_message_reorder_with_identical_signatures_is_breaking(self):
        self.assert_break(protocol(FIRST + SECOND), protocol(SECOND + FIRST))

    def test_same_version_insertion_moves_wire_opcode(self):
        inserted = '<request name="inserted"><arg name="value" type="uint"/></request>'
        self.assert_break(protocol(FIRST + SECOND), protocol(inserted + FIRST + SECOND))

    def test_event_opcode_insertion_is_breaking(self):
        inserted = '<event name="inserted"><arg name="value" type="uint"/></event>'
        self.assert_break(protocol(FIRST + TICK + DONE), protocol(FIRST + inserted + TICK + DONE))

    def test_request_and_event_opcode_sequences_are_independent(self):
        self.assert_clear(
            protocol(FIRST + SECOND + TICK + DONE),
            protocol(TICK + FIRST + DONE + SECOND),
        )

    def test_since_gated_tail_addition_requires_review_without_structural_break(self):
        added = '<request name="third" since="2"><arg name="value" type="uint"/></request>'
        _, data = self.compare(protocol(FIRST + SECOND), protocol(FIRST + SECOND + added, 2), 3)
        self.assertEqual(data["verdict"], "needs_review")
        self.assertFalse(any(f["severity"] == "break" for f in data["findings"]), data)

    def test_new_request_cannot_retroactively_exist_in_old_version(self):
        self.assert_break(protocol(FIRST), protocol(FIRST + SECOND, 2))

    def test_interface_version_cannot_decrease(self):
        self.assert_break(protocol(FIRST, 2), protocol(FIRST, 1))

    def test_argument_type_change_is_breaking(self):
        changed = FIRST.replace('type="uint"', 'type="int"')
        self.assert_break(protocol(FIRST), protocol(changed), "first")

    def test_argument_order_change_is_breaking(self):
        old = '<request name="set"><arg name="x" type="uint"/><arg name="label" type="string"/></request>'
        new = '<request name="set"><arg name="label" type="string"/><arg name="x" type="uint"/></request>'
        self.assert_break(protocol(old), protocol(new), "set")

    def test_nullability_change_is_not_silently_clear(self):
        old = '<event name="label"><arg name="text" type="string"/></event>'
        new = old.replace('type="string"', 'type="string" allow-null="true"')
        self.assert_break(protocol(old), protocol(new), "label")

    def test_destructor_lifetime_change_is_breaking(self):
        old = '<request name="close"/>'
        new = '<request name="close" type="destructor"/>'
        self.assert_break(protocol(old), protocol(new), "close")

    def test_typed_to_generic_new_id_changes_wire_shape(self):
        old = '<request name="create"><arg name="id" type="new_id" interface="example_child_v1"/></request>'
        new = '<request name="create"><arg name="id" type="new_id"/></request>'
        child = '<interface name="example_child_v1" version="1"><request name="destroy" type="destructor"/></interface>'
        self.assert_break(
            protocol(old).replace('</protocol>', child + '</protocol>'),
            protocol(new).replace('</protocol>', child + '</protocol>'),
            "create",
        )

    def test_generic_to_typed_new_id_changes_wire_shape(self):
        generic = '<request name="create"><arg name="id" type="new_id"/></request>'
        typed = '<request name="create"><arg name="id" type="new_id" interface="example_child_v1"/></request>'
        child = '<interface name="example_child_v1" version="1"><request name="destroy" type="destructor"/></interface>'
        self.assert_break(
            protocol(generic).replace('</protocol>', child + '</protocol>'),
            protocol(typed).replace('</protocol>', child + '</protocol>'),
            "create",
        )

    def test_enum_integer_spellings_are_semantically_equivalent(self):
        for alternate in ("010", "0x8"):
            with self.subTest(alternate=alternate):
                enum = '<enum name="state"><entry name="ready" value="{}"/></enum>'
                self.assert_clear(protocol(FIRST + enum.format("8")),
                                  protocol(FIRST + enum.format(alternate)))

    def test_existing_enum_numeric_value_change_is_breaking(self):
        # Mirrors the class of the upstream ext-background-effect blur=0 fix;
        # a structural report cannot infer whether an already broken bit was used.
        enum = '<enum name="capability" bitfield="true"><entry name="blur" value="{}"/></enum>'
        self.assert_break(protocol(FIRST + enum.format("0")),
                          protocol(FIRST + enum.format("1")), "blur")

    def test_enum_bitfield_change_is_breaking(self):
        enum = '<enum name="state"><entry name="ready" value="1"/></enum>'
        self.assert_break(protocol(FIRST + enum),
                          protocol(FIRST + enum.replace('name="state"', 'name="state" bitfield="true"')),
                          "state")

    def test_prose_change_requires_human_review(self):
        old_doc = '<description summary="behavior">The request applies immediately.</description>'
        new_doc = '<description summary="behavior">The request applies on commit.</description>'
        _, data = self.compare(protocol(FIRST, description=old_doc),
                               protocol(FIRST, description=new_doc), 3)
        self.assertEqual(data["verdict"], "needs_review")
        self.assertTrue(any(f["severity"] == "review" for f in data["findings"]))
        self.assertFalse(any(f["severity"] == "break" for f in data["findings"]))

    def test_breaking_change_takes_precedence_over_prose_review(self):
        old = protocol(FIRST, description='<description summary="behavior">Old behavior.</description>')
        new = protocol(FIRST.replace('type="uint"', 'type="int"'),
                       description='<description summary="behavior">New behavior.</description>')
        self.assert_break(old, new)

    def test_directory_resolves_external_interface_in_same_input_bundle(self):
        old_dir = self.base / "old-bundle"
        new_dir = self.base / "new-bundle"
        old_dir.mkdir()
        new_dir.mkdir()
        factory = protocol('<request name="create"><arg name="id" type="new_id" interface="example_child_v1"/></request>')
        child = '<protocol name="child"><interface name="example_child_v1" version="1"><request name="destroy" type="destructor"/></interface></protocol>'
        for directory in (old_dir, new_dir):
            (directory / "factory.xml").write_text(factory, encoding="utf-8")
            (directory / "child.xml").write_text(child, encoding="utf-8")
        _, data = self.run_compare(old_dir, new_dir, 0)
        self.assertEqual(data["verdict"], "no_structural_hazards")
        self.assertEqual(len(data["old"]["sources"]), 2)

    def test_duplicate_interface_in_bundle_is_invalid(self):
        old_dir = self.base / "duplicate"
        old_dir.mkdir()
        for filename in ("a.xml", "b.xml"):
            (old_dir / filename).write_text(protocol(FIRST), encoding="utf-8")
        self.new.write_text(protocol(FIRST), encoding="utf-8")
        self.run_compare(old_dir, self.new, 2)

    def test_missing_input_fails_clearly(self):
        self.new.write_text(protocol(FIRST), encoding="utf-8")
        self.run_compare(self.base / "missing.xml", self.new, 2)

    def test_empty_bundle_is_invalid(self):
        empty_dir = self.base / "empty"
        empty_dir.mkdir()
        self.new.write_text(protocol(FIRST), encoding="utf-8")
        self.run_compare(empty_dir, self.new, 2)

    def test_malformed_xml_is_invalid(self):
        self.compare(protocol(FIRST), '<protocol name="broken">', 2)

    def test_xml_entities_are_rejected_without_expansion(self):
        malicious = (
            '<!DOCTYPE protocol [<!ENTITY unsafe SYSTEM "file:///etc/passwd">]>'
            '<protocol name="example"><interface name="example_factory_v1" version="1">'
            '<description summary="secret">&unsafe;</description>' + FIRST +
            '</interface></protocol>'
        )
        result, _ = self.compare(protocol(FIRST), malicious, 2)
        self.assertNotIn("root:x:", result.stdout + result.stderr)

    def test_internal_entity_declarations_are_rejected(self):
        xml = '<!DOCTYPE protocol [<!ENTITY x "expanded">]>' + protocol(FIRST).split('\n', 1)[1]
        self.compare(protocol(FIRST), xml, 2)

    def test_invalid_interface_versions_fail_closed(self):
        for version in ("0", "-1", "x"):
            with self.subTest(version=version):
                self.compare(protocol(FIRST), protocol(FIRST, version), 2)

    def test_future_since_beyond_interface_version_is_invalid(self):
        xml = protocol('<request name="first" since="2"/>', 1)
        self.compare(protocol(FIRST), xml, 2)

    def test_nullability_on_integer_is_invalid(self):
        xml = protocol('<request name="first"><arg name="value" type="uint" allow-null="true"/></request>')
        self.compare(protocol(FIRST), xml, 2)

    def test_generic_new_id_event_is_invalid(self):
        xml = protocol('<event name="created"><arg name="id" type="new_id"/></event>')
        self.compare(protocol(FIRST), xml, 2)

    def test_unknown_semantic_attribute_fails_closed(self):
        xml = protocol(FIRST).replace('<request name="first"', '<request name="first" future-wire-mode="true"')
        self.compare(protocol(FIRST), xml, 2)

    def test_repeated_reports_and_source_hashes_are_deterministic(self):
        xml = protocol(FIRST + TICK)
        first, data = self.compare(xml, xml, 0)
        second, _ = self.run_compare(self.old, self.new, 0)
        self.assertEqual(first.stdout, second.stdout)
        digest = hashlib.sha256(xml.encode("utf-8")).hexdigest()
        self.assertEqual(data["old"]["sources"][0]["sha256"], digest)
        self.assertEqual(data["new"]["sources"][0]["sha256"], digest)

    def test_report_publication_never_overwrites_existing_file(self):
        self.old.write_text(protocol(FIRST), encoding="utf-8")
        self.new.write_text(protocol(FIRST), encoding="utf-8")
        report = self.base / "report.json"
        sentinel = b"keep this exact existing report\n"
        report.write_bytes(sentinel)
        result = self.invoke(self.old, self.new, ("--output", str(report)))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(report.read_bytes(), sentinel)
        self.assertNotIn("Traceback (most recent call last)", result.stderr)

    def test_report_publication_cannot_overwrite_an_input(self):
        xml = protocol(FIRST)
        self.old.write_text(xml, encoding="utf-8")
        self.new.write_text(xml, encoding="utf-8")
        before = self.old.read_bytes()
        result = self.invoke(self.old, self.new, ("--output", str(self.old)))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.old.read_bytes(), before)

    def test_new_report_file_contains_complete_json(self):
        self.old.write_text(protocol(FIRST), encoding="utf-8")
        self.new.write_text(protocol(FIRST), encoding="utf-8")
        report = self.base / "new-report.json"
        result = self.invoke(self.old, self.new, ("--output", str(report)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["verdict"],
                         "no_structural_hazards")
        self.assertFalse(list(self.base.glob(".wl-contract-*")))

    def test_invalid_input_does_not_publish_partial_report(self):
        self.old.write_text('<protocol name="broken">', encoding="utf-8")
        self.new.write_text(protocol(FIRST), encoding="utf-8")
        report = self.base / "should-not-exist.json"
        result = self.invoke(self.old, self.new, ("--output", str(report)))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(report.exists())
        self.assertFalse(list(self.base.glob(".wl-contract-*")))

    def symlink_or_skip(self, link, target, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (NotImplementedError, OSError) as error:
            self.skipTest("Creating symlinks is unavailable: {}".format(error))

    def test_symlink_input_is_rejected(self):
        self.old.write_text(protocol(FIRST), encoding="utf-8")
        self.new.write_text(protocol(FIRST), encoding="utf-8")
        linked = self.base / "linked.xml"
        self.symlink_or_skip(linked, self.old)
        self.run_compare(linked, self.new, 2)

    def test_symlink_inside_directory_tree_is_rejected(self):
        directory = self.base / "bundle-with-link"
        directory.mkdir()
        self.old.write_text(protocol(FIRST), encoding="utf-8")
        self.new.write_text(protocol(FIRST), encoding="utf-8")
        self.symlink_or_skip(directory / "external.xml", self.old)
        self.run_compare(directory, self.new, 2)

    def test_oversize_file_is_rejected_before_parsing(self):
        self.old.write_bytes(b" " * (4 * 1024 * 1024 + 1))
        self.new.write_text(protocol(FIRST), encoding="utf-8")
        result, _ = self.run_compare(self.old, self.new, 2)
        self.assertIn("bytes", result.stderr.lower())

    def test_too_many_xml_files_are_rejected(self):
        directory = self.base / "too-many-files"
        directory.mkdir()
        for index in range(257):
            (directory / "{}.xml".format(index)).write_text(protocol(FIRST), encoding="utf-8")
        self.new.write_text(protocol(FIRST), encoding="utf-8")
        result, _ = self.run_compare(directory, self.new, 2)
        self.assertIn("256", result.stderr)

    def test_utf16_input_is_rejected(self):
        self.old.write_bytes(protocol(FIRST).replace('encoding="UTF-8"', 'encoding="UTF-16"').encode("utf-16"))
        self.new.write_text(protocol(FIRST), encoding="utf-8")
        self.run_compare(self.old, self.new, 2)


if __name__ == "__main__":
    unittest.main()
