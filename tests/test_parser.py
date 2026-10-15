"""Public parsing checks for protocol meaning and hostile input boundaries."""

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from wl_contract.parser import InputError, load_snapshot


def protocol(body, version=1, attrs="", name="example", interface="example_v1"):
    return (
        '<protocol name="{}"><interface name="{}" version="{}" {}>{}</interface></protocol>'
    ).format(name, interface, version, attrs, body)


class ParserTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="wl-contract-parser-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.file = self.directory / "fixture.xml"

    def parse(self, xml):
        self.file.write_text(xml, encoding="utf-8")
        return load_snapshot(self.file)

    def invalid(self, xml, reason):
        with self.assertRaisesRegex(InputError, reason):
            self.parse(xml)

    def test_opcodes_count_each_direction_independently(self):
        result = self.parse(protocol(
            '<request name="first"/><event name="tick"/>'
            '<enum name="values"><entry name="one" value="1"/></enum>'
            '<event name="done"/><request name="last"/>'
        ))["interfaces"]["example_v1"]
        self.assertEqual([(m["name"], m["opcode"]) for m in result["requests"]],
                         [("first", 0), ("last", 1)])
        self.assertEqual([(m["name"], m["opcode"]) for m in result["events"]],
                         [("tick", 0), ("done", 1)])

    def test_provenance_hashes_original_utf8_bytes(self):
        xml = protocol('<request name="run"/>')
        self.file.write_bytes(b"\xef\xbb\xbf" + xml.encode("utf-8"))
        result = load_snapshot(self.file)
        self.assertEqual(result["sources"], [{
            "path": "fixture.xml", "sha256": hashlib.sha256(self.file.read_bytes()).hexdigest(),
        }])
        self.assertEqual(result["interfaces"]["example_v1"]["source"], "fixture.xml")
        self.assertEqual(result["interfaces"]["example_v1"]["protocol"], "example")

    def test_summary_and_description_whitespace_normalize(self):
        result = self.parse(protocol(
            '<request name="run"><description summary=" do   work ">'
            ' first\nsecond </description>'
            '<arg name="target" type="object" summary=" target   object ">'
            '<description summary=" detailed "> body </description></arg></request>'
        ))["interfaces"]["example_v1"]["requests"][0]
        self.assertEqual(result["description"], "do work first second")
        self.assertEqual(result["args"][0]["description"], "target object detailed body")

    def test_external_object_and_enum_contracts_remain_literal(self):
        result = self.parse(protocol(
            '<request name="run"><arg name="object" type="object" interface="external_v1"/>'
            '<arg name="code" type="uint" enum="external_v1.code"/></request>'
        ))["interfaces"]["example_v1"]["requests"][0]
        self.assertEqual(result["args"][0]["interface"], "external_v1")
        self.assertEqual(result["args"][1]["enum"], "external_v1.code")

    def test_missing_enum_on_supplied_interface_is_invalid(self):
        self.invalid(protocol('<request name="run"><arg name="x" type="uint" enum="missing"/></request>'),
                     "has no enum")

    def test_supplied_cross_interface_enum_must_exist(self):
        xml = ('<protocol name="example"><interface name="one" version="1">'
               '<request name="run"><arg name="x" type="uint" enum="two.missing"/></request>'
               '</interface><interface name="two" version="1"><event name="done"/>'
               '</interface></protocol>')
        self.invalid(xml, "has no enum")

    def test_known_bitfield_reference_requires_uint(self):
        self.invalid(protocol(
            '<request name="run"><arg name="x" type="int" enum="flags"/></request>'
            '<enum name="flags" bitfield="true"><entry name="flag" value="1"/></enum>'
        ), "bitfield enum references require uint")

    def test_enum_integer_bases_and_boundaries(self):
        for raw, expected in [("01", 1), ("0x1", 1), ("010", 8), ("0", 0),
                              ("-0x1", -1), ("-2147483648", -(2**31)),
                              ("0xffffffff", 2**32 - 1)]:
            with self.subTest(value=raw):
                result = self.parse(protocol(
                    '<enum name="code"><entry name="1st" value="{}"/></enum>'.format(raw)
                ))
                self.assertEqual(result["interfaces"]["example_v1"]["enums"]["code"]
                                 ["entries"]["1st"]["value"], expected)

    def test_enum_requires_consistent_integer_domain(self):
        self.invalid(protocol(
            '<enum name="code"><entry name="negative" value="-1"/>'
            '<entry name="large" value="0xffffffff"/></enum>'
        ), "one signed or unsigned")

    def test_enum_and_entry_since_are_independent(self):
        result = self.parse(protocol(
            '<enum name="code" since="2"><entry name="one" value="1"/></enum>', version=2
        ))["interfaces"]["example_v1"]["enums"]["code"]
        self.assertEqual(result["since"], 2)
        self.assertEqual(result["entries"]["one"]["since"], 1)

    def test_unsupported_integer_values_fail(self):
        for raw in ["09", "0x", "1U", "1 &lt;&lt; 2", "4294967296", "-2147483649", ""]:
            with self.subTest(value=raw):
                self.invalid(protocol('<enum name="code"><entry name="x" value="{}"/></enum>'.format(raw)),
                             "value")

    def test_empty_and_negative_bitfield_enumerations_fail(self):
        self.invalid(protocol('<enum name="code"/>'), "empty enumerations")
        self.invalid(protocol('<enum name="flags" bitfield="true"><entry name="x" value="-1"/></enum>'),
                     "32-bit")

    def test_effective_defaults_and_explicit_false(self):
        iface = self.parse(protocol('<request name="run"><arg name="x" type="string" '
                                    'allow-null="false"/></request>', attrs='frozen="false"'))[
                                        "interfaces"]["example_v1"]
        self.assertFalse(iface["frozen"])
        self.assertEqual(iface["requests"][0]["since"], 1)
        self.assertIsNone(iface["requests"][0]["deprecated_since"])
        self.assertFalse(iface["requests"][0]["args"][0]["allow_null"])

    def test_frozen_interface_stays_at_one(self):
        self.parse(protocol('<request name="run"/>', attrs='frozen="true"'))
        self.invalid(protocol('<request name="run"/>', version=2, attrs='frozen="true"'), "frozen")

    def test_version_and_deprecation_bounds(self):
        for version in ["0", "-1", "1.0", "2147483648", "1x", ""]:
            with self.subTest(version=version):
                self.invalid(protocol('<request name="run"/>', version=version), "version")
        self.invalid(protocol('<request name="run" since="2"/>'), "since exceeds")
        self.invalid(protocol('<request name="run" deprecated-since="1"/>'), "greater than since")
        self.invalid(protocol('<request name="run" deprecated-since="3"/>', version=2), "exceeds")
        # A long spelling cannot leak Python's integer conversion limit error.
        self.invalid(protocol('<request name="run"/>', version="0" * 5000), "between 1")

    def test_decreasing_since_between_directions_is_valid(self):
        self.parse(protocol('<request name="added" since="2"/><event name="original"/>', version=2))

    def test_message_and_argument_names_are_unique(self):
        self.invalid(protocol('<request name="run"/><event name="run"/>'), "duplicate request/event")
        self.invalid(protocol('<request name="run"><arg name="x" type="uint"/>'
                              '<arg name="x" type="uint"/></request>'), "duplicate argument")

    def test_duplicate_enumeration_names_and_entries_fail(self):
        enum = '<enum name="code"><entry name="x" value="1"/></enum>'
        self.invalid(protocol(enum + enum), "duplicate enum")
        self.invalid(protocol('<enum name="code"><entry name="x" value="1"/>'
                              '<entry name="x" value="2"/></enum>'), "duplicate entry")

    def test_argument_type_restrictions(self):
        for argument, reason in [
            ('<arg name="x" type="unknown"/>', "unsupported type"),
            ('<arg name="x" type="fd" allow-null="false"/>', "allow-null"),
            ('<arg name="x" type="uint" interface="external"/>', "interface requires"),
            ('<arg name="x" type="object" enum="code"/>', "enum requires"),
            ('<arg name="x" type="uint" enum="a.b.c"/>', "invalid enum reference"),
        ]:
            with self.subTest(argument=argument):
                self.invalid(protocol('<request name="run">' + argument + '</request>'), reason)

    def test_constructor_and_message_argument_limits(self):
        self.parse(protocol('<request name="create"><arg name="id" type="new_id"/></request>'))
        self.invalid(protocol('<event name="created"><arg name="id" type="new_id"/></event>'),
                     "explicit interface")
        self.invalid(protocol('<request name="create"><arg name="one" type="new_id"/>'
                              '<arg name="two" type="new_id"/></request>'), "at most one")
        twenty = ''.join('<arg name="a{}" type="uint"/>'.format(i) for i in range(20))
        self.parse(protocol('<request name="run">' + twenty + '</request>'))
        self.invalid(protocol('<request name="run">' + twenty + '<arg name="extra" type="uint"/>'
                              '</request>'), "more than 20")

    def test_destroy_must_be_a_destructor(self):
        self.invalid(protocol('<request name="destroy"/>'), "destructor")
        self.invalid(protocol('<request name="run" type="something"/>'), "type must be destructor")

    def test_generic_constructor_expansion_counts_toward_runtime_limit(self):
        prefix = ''.join('<arg name="a{}" type="uint"/>'.format(i) for i in range(17))
        constructor = '<arg name="id" type="new_id"/>'
        self.parse(protocol('<request name="create">' + prefix + constructor + '</request>'))
        self.invalid(protocol('<request name="create">' + prefix + constructor
                              + '<arg name="extra" type="uint"/></request>'), "expanded wire arguments")

    def test_strict_vocabulary_and_description_placement(self):
        for xml, reason in [
            (protocol('<request name="run" other="value"/>'), "unsupported attribute"),
            (protocol('<unknown/>'), "unsupported XML element"),
            (protocol('<request name="run"><description>text</description></request>'), "missing required"),
            (protocol('<request name="run"/><description summary="late"/>'), "unexpected child"),
            (protocol('<request name="run"/>').replace('<protocol ', '<protocol xmlns:unused="urn:x" '), "namespaces"),
            (protocol('<request name="run"/>').replace('<protocol ', '<protocol xmlns="urn:x" '), "namespaces"),
        ]:
            with self.subTest(reason=reason):
                self.invalid(xml, reason)

    def test_xml_cannot_fetch_or_expand_declared_entities(self):
        for declaration in ['<!DOCTYPE protocol SYSTEM "file:///definitely-not-a-file">',
                            '<!DOCTYPE protocol [<!ENTITY local "content">]>']:
            self.invalid(declaration + protocol('<request name="run"/>'), "DOCTYPE")

    def test_encoding_boundary_is_utf8(self):
        self.invalid('<?xml version="1.0" encoding="ISO-8859-1"?>' + protocol('<request name="run"/>'),
                     "UTF-8")
        self.file.write_bytes(protocol('<request name="run"/>').encode("utf-16"))
        with self.assertRaisesRegex(InputError, "UTF-8"):
            load_snapshot(self.file)

    def test_xml_depth_and_element_count_are_bounded(self):
        self.invalid('<protocol name="example">' + '<description summary="x">' * 16
                     + '</description>' * 16 + '</protocol>', "depth exceeds 16")
        self.invalid(protocol('<request name="r"/>' * 50_000), "more than 50000 XML elements")

    def test_recursive_paths_are_sorted_and_relative(self):
        nested = self.directory / "nested"
        nested.mkdir()
        (nested / "a.xml").write_text(protocol('<request name="run"/>'))
        (self.directory / "z.xml").write_text(protocol('<event name="done"/>', name="two", interface="two"))
        result = load_snapshot(self.directory)
        self.assertEqual([source["path"] for source in result["sources"]], ["nested/a.xml", "z.xml"])

    def test_duplicate_protocol_identity_in_tree_fails(self):
        self.file.write_text(protocol('<request name="run"/>'))
        (self.directory / "other.xml").write_text(protocol('<event name="done"/>', interface="two"))
        with self.assertRaisesRegex(InputError, "duplicate protocol"):
            load_snapshot(self.directory)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_directory_and_nonxml_symlinks_fail(self):
        self.file.write_text(protocol('<request name="run"/>'))
        outside = self.directory.parent / (self.directory.name + "-link")
        try:
            outside.symlink_to(self.directory, target_is_directory=True)
        except OSError as error:
            self.skipTest("Creating symlinks is unavailable: {}".format(error))
        self.addCleanup(outside.unlink)
        with self.assertRaisesRegex(InputError, "symlink"):
            load_snapshot(outside)
        (self.directory / "ignored.txt").symlink_to(self.file)
        with self.assertRaisesRegex(InputError, "symlink"):
            load_snapshot(self.directory)

    def test_filesystem_depth_is_bounded(self):
        deepest = self.directory
        for index in range(16):
            deepest = deepest / str(index)
            deepest.mkdir()
        (deepest / "file.xml").write_text(protocol('<request name="run"/>'))
        with self.assertRaisesRegex(InputError, "directory depth exceeds 16"):
            load_snapshot(self.directory)

    def test_nonxml_directory_entries_are_also_bounded(self):
        self.file.write_text(protocol('<request name="run"/>'))
        for index in range(4096):
            (self.directory / str(index)).touch()
        with self.assertRaisesRegex(InputError, "more than 4096 filesystem entries"):
            load_snapshot(self.directory)

    @unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(os, "O_NONBLOCK"), "FIFO unavailable")
    def test_file_replaced_by_fifo_before_open_fails_without_blocking(self):
        self.file.write_text(protocol('<request name="run"/>'))
        original_open = os.open

        def replace_before_open(path, flags, *args, **kwargs):
            if Path(path) == self.file:
                self.assertTrue(flags & os.O_NONBLOCK)
                self.file.unlink()
                os.mkfifo(self.file)
            return original_open(path, flags, *args, **kwargs)

        with mock.patch("wl_contract.parser.os.open", side_effect=replace_before_open):
            with self.assertRaisesRegex(InputError, "regular file"):
                load_snapshot(self.file)

    def test_total_snapshot_bytes_are_bounded(self):
        for index in range(9):
            xml = protocol('<request name="run"/>', name="p{}".format(index), interface="i{}".format(index))
            (self.directory / "{}.xml".format(index)).write_text(xml + " " * (4 * 1024 * 1024 - len(xml)))
        with self.assertRaisesRegex(InputError, "snapshot exceeds 33554432 bytes"):
            load_snapshot(self.directory)


if __name__ == "__main__":
    unittest.main()
