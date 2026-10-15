"""Read bounded Wayland XML snapshots without executing or fetching anything.

This module accepts the documented Wayland XML vocabulary, not arbitrary XML.
External interface and enum references remain literal names; their definitions
need not be present in a snapshot.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any
import xml.etree.ElementTree as ET


MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_FILES = 256
MAX_TREE_ENTRIES = 4096
MAX_ELEMENTS = 50_000
MAX_DEPTH = 16
MAX_VERSION = 2**31 - 1


class InputError(ValueError):
    """An input is malformed, unsupported, or exceeds the stated limits."""


_IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z", re.ASCII)
_SUFFIX = re.compile(r"[A-Za-z_0-9]+\Z", re.ASCII)
_ENUM_REF = re.compile(
    r"(?:[A-Za-z_][A-Za-z_0-9]*\.)?[A-Za-z_0-9]+\Z", re.ASCII
)
_DECIMAL = re.compile(r"[0-9]+\Z", re.ASCII)
_VALUE = re.compile(r"([+-]?)(0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)\Z", re.ASCII)
_DECLARATION = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_ENCODING = re.compile(r"^\s*<\?xml\s+[^?]*\bencoding\s*=\s*(['\"])(.*?)\1", re.IGNORECASE)
_TYPES = {"int", "uint", "fixed", "string", "object", "new_id", "array", "fd"}
_ATTRS = {
    "protocol": {"name"},
    "copyright": set(),
    "description": {"summary"},
    "interface": {"name", "version", "frozen"},
    "request": {"name", "type", "since", "deprecated-since"},
    "event": {"name", "type", "since", "deprecated-since"},
    "arg": {"name", "type", "interface", "allow-null", "enum", "summary"},
    "enum": {"name", "since", "bitfield"},
    "entry": {"name", "value", "since", "deprecated-since", "summary"},
}
_REQUIRED = {
    "protocol": {"name"},
    "copyright": set(),
    "description": {"summary"},
    "interface": {"name", "version"},
    "request": {"name"},
    "event": {"name"},
    "arg": {"name", "type"},
    "enum": {"name"},
    "entry": {"name", "value"},
}


def _error(path: str, message: str) -> InputError:
    return InputError(f"{path}: {message}")


class _BoundedTree(ET.TreeBuilder):
    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.elements = 0
        self.depth = 0

    def start(self, tag: str, attrs: dict[str, str]) -> ET.Element:
        self.elements += 1
        self.depth += 1
        if self.elements > MAX_ELEMENTS:
            raise _error(self.path, f"more than {MAX_ELEMENTS} XML elements")
        if self.depth > MAX_DEPTH:
            raise _error(self.path, f"XML depth exceeds {MAX_DEPTH}")
        return super().start(tag, attrs)

    def end(self, tag: str) -> ET.Element:
        element = super().end(tag)
        self.depth -= 1
        return element

    def start_ns(self, prefix: str, uri: str) -> None:
        raise _error(self.path, "XML namespaces are unsupported")


def _files(root: Path) -> list[tuple[Path, str]]:
    """List regular input files, rejecting symlinks anywhere in a tree."""
    try:
        mode = root.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise _error(root.name or str(root), "symlink inputs are unsupported")
        if stat.S_ISREG(mode):
            return [(root, root.name)]
        if not stat.S_ISDIR(mode):
            raise _error(root.name or str(root), "expected a regular file or directory")
        found: list[tuple[Path, str]] = []
        pending = [(root, 1)]
        count = 0
        while pending:
            directory, depth = pending.pop()
            with os.scandir(directory) as entries:
                for child in entries:
                    count += 1
                    if count > MAX_TREE_ENTRIES:
                        raise _error(root.name, f"more than {MAX_TREE_ENTRIES} filesystem entries")
                    path = Path(child.path)
                    relative = path.relative_to(root).as_posix()
                    mode = child.stat(follow_symlinks=False).st_mode
                    if stat.S_ISLNK(mode):
                        raise _error(relative, "symlinks in input trees are unsupported")
                    if stat.S_ISDIR(mode):
                        if depth >= MAX_DEPTH:
                            raise _error(relative, f"directory depth exceeds {MAX_DEPTH}")
                        pending.append((path, depth + 1))
                    elif stat.S_ISREG(mode):
                        if path.suffix == ".xml":
                            found.append((path, relative))
                            if len(found) > MAX_FILES:
                                raise _error(root.name, f"more than {MAX_FILES} XML files")
                    else:
                        raise _error(relative, "non-regular files in input trees are unsupported")
        if not found:
            raise _error(root.name, "directory contains no *.xml files")
        return sorted(found, key=lambda item: item[1])
    except InputError:
        raise
    except (OSError, ValueError) as exc:
        raise _error(root.name or str(root), f"cannot inspect input ({exc.strerror if isinstance(exc, OSError) else exc})") from exc


def _read(path: Path, relative: str) -> bytes:
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise _error(relative, "expected a regular file")
            if info.st_size > MAX_FILE_BYTES:
                raise _error(relative, f"file exceeds {MAX_FILE_BYTES} bytes")
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise _error(relative, f"file exceeds {MAX_FILE_BYTES} bytes")
        return data
    except InputError:
        raise
    except OSError as exc:
        raise _error(relative, f"cannot read input ({exc.strerror})") from exc


def _tree(data: bytes, path: str) -> ET.Element:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _error(path, "input must be UTF-8 XML") from exc
    if _DECLARATION.search(text):
        raise _error(path, "DOCTYPE and ENTITY declarations are unsupported")
    encoding = _ENCODING.search(text)
    if encoding and encoding.group(2).lower() not in {"utf-8", "utf8"}:
        raise _error(path, "XML encoding declaration must specify UTF-8")
    try:
        parser = ET.XMLParser(target=_BoundedTree(path))
        root = ET.fromstring(text, parser=parser)
    except InputError:
        raise
    except (ET.ParseError, ValueError) as exc:
        raise _error(path, f"malformed XML ({exc})") from exc
    for element in root.iter():
        tag = element.tag
        if not isinstance(tag, str) or tag not in _ATTRS:
            raise _error(path, f"unsupported XML element {tag!r}; namespaces are unsupported")
        unknown = set(element.attrib) - _ATTRS[tag]
        missing = _REQUIRED[tag] - set(element.attrib)
        if unknown:
            raise _error(path, f"{tag}: unsupported attribute {sorted(unknown)[0]!r}")
        if missing:
            raise _error(path, f"{tag}: missing required attribute {sorted(missing)[0]!r}")
        if tag not in {"description", "copyright"} and element.text and element.text.strip():
            raise _error(path, f"{tag}: unexpected text content")
        if element.tail and element.tail.strip():
            raise _error(path, f"{tag}: unexpected text after element")
    if root.tag != "protocol":
        raise _error(path, "root element must be protocol")
    return root


def _name(element: ET.Element, path: str, suffix: bool = False) -> str:
    value = element.attrib["name"]
    if not (_SUFFIX if suffix else _IDENT).fullmatch(value):
        raise _error(path, f"{element.tag}: invalid name {value!r}")
    return value


def _positive(element: ET.Element, attr: str, path: str, default: int | None = None) -> int:
    raw = element.get(attr)
    if raw is None and default is not None:
        return default
    if raw is None or not _DECIMAL.fullmatch(raw):
        raise _error(path, f"{element.tag}: {attr} must be a positive decimal integer")
    # Avoid converting an attacker-controlled thousands-digit integer.
    if len(raw.lstrip("0")) > 10:
        raise _error(path, f"{element.tag}: {attr} exceeds {MAX_VERSION}")
    value = int(raw.lstrip("0") or "0")
    if not 1 <= value <= MAX_VERSION:
        raise _error(path, f"{element.tag}: {attr} must be between 1 and {MAX_VERSION}")
    return value


def _bool(element: ET.Element, attr: str, path: str) -> bool:
    value = element.get(attr, "false")
    if value not in {"true", "false"}:
        raise _error(path, f"{element.tag}: {attr} must be true or false")
    return value == "true"


def _versions(element: ET.Element, version: int, path: str) -> tuple[int, int | None]:
    since = _positive(element, "since", path, 1)
    deprecated = None
    if "deprecated-since" in element.attrib:
        deprecated = _positive(element, "deprecated-since", path)
        if deprecated <= since:
            raise _error(path, f"{element.tag}: deprecated-since must be greater than since")
        if deprecated > version:
            raise _error(path, f"{element.tag}: deprecated-since exceeds interface version")
    if since > version:
        raise _error(path, f"{element.tag}: since exceeds interface version")
    return since, deprecated


def _children(element: ET.Element, allowed: set[str], path: str, description: bool = True) -> list[ET.Element]:
    children = list(element)
    for index, child in enumerate(children):
        if child.tag == "description" and description and index == 0:
            if list(child):
                raise _error(path, "description cannot contain XML elements")
            continue
        if child.tag not in allowed:
            raise _error(path, f"{element.tag}: unexpected child {child.tag!r}")
    return [child for child in children if child.tag != "description"]


def _description(element: ET.Element) -> str:
    parts = [element.get("summary", "")]
    desc = element.find("description")
    if desc is not None:
        parts.extend([desc.get("summary", ""), desc.text or ""])
    return " ".join(" ".join(parts).split())


def _argument(element: ET.Element, path: str) -> dict[str, Any]:
    _children(element, set(), path)
    name = _name(element, path)
    kind = element.attrib["type"]
    if kind not in _TYPES:
        raise _error(path, f"arg {name!r}: unsupported type {kind!r}")
    target = element.get("interface")
    if target is not None:
        if kind not in {"object", "new_id"}:
            raise _error(path, f"arg {name!r}: interface requires object or new_id type")
        if not _IDENT.fullmatch(target):
            raise _error(path, f"arg {name!r}: invalid interface reference {target!r}")
    nullable = _bool(element, "allow-null", path)
    if "allow-null" in element.attrib and kind not in {"string", "object"}:
        raise _error(path, f"arg {name!r}: allow-null is only supported for string or object")
    enum = element.get("enum")
    if enum is not None:
        if not _ENUM_REF.fullmatch(enum):
            raise _error(path, f"arg {name!r}: invalid enum reference {enum!r}")
        if kind not in {"int", "uint"}:
            raise _error(path, f"arg {name!r}: enum requires int or uint type")
    return {"name": name, "type": kind, "interface": target, "allow_null": nullable,
            "enum": enum, "description": _description(element)}


def _message(element: ET.Element, opcode: int, version: int, path: str) -> dict[str, Any]:
    children = _children(element, {"arg"}, path)
    name = _name(element, path)
    if len(children) > 20:
        raise _error(path, f"{element.tag} {name!r}: more than 20 arguments")
    kind = element.get("type")
    if kind is not None and kind != "destructor":
        raise _error(path, f"{element.tag} {name!r}: type must be destructor when present")
    if name == "destroy" and kind != "destructor":
        raise _error(path, f"{element.tag} 'destroy' must have type destructor")
    since, deprecated = _versions(element, version, path)
    arguments = [_argument(child, path) for child in children]
    names: set[str] = set()
    for argument in arguments:
        if argument["name"] in names:
            raise _error(path, f"{element.tag} {name!r}: duplicate argument {argument['name']!r}")
        names.add(argument["name"])
    new_ids = [arg for arg in arguments if arg["type"] == "new_id"]
    if len(new_ids) > 1:
        raise _error(path, f"{element.tag} {name!r}: at most one new_id argument is supported")
    if element.tag == "event" and any(arg["interface"] is None for arg in new_ids):
        raise _error(path, f"event {name!r}: new_id requires an explicit interface")
    expanded_count = len(arguments) + 2 * sum(arg["interface"] is None for arg in new_ids)
    if expanded_count > 20:
        raise _error(path, f"{element.tag} {name!r}: more than 20 expanded wire arguments (generic new_id adds two)")
    return {"name": name, "opcode": opcode, "since": since, "deprecated_since": deprecated,
            "destructor": kind == "destructor", "description": _description(element), "args": arguments}


def _entry(element: ET.Element, version: int, bitfield: bool, path: str) -> dict[str, Any]:
    _children(element, set(), path)
    name = _name(element, path, suffix=True)
    raw = element.attrib["value"]
    match = _VALUE.fullmatch(raw)
    if not match:
        raise _error(path, f"entry {name!r}: value must be a decimal, hexadecimal, or octal integer")
    sign, number = match.groups()
    digits = number[2:] if number.lower().startswith("0x") else number
    if len(digits.lstrip("0")) > 32:
        raise _error(path, f"entry {name!r}: value exceeds 32-bit integer range")
    base = 16 if number.lower().startswith("0x") else 8 if number.startswith("0") else 10
    value = int(number, base) * (-1 if sign == "-" else 1)
    minimum = 0 if bitfield else -(2**31)
    if not minimum <= value <= 2**32 - 1:
        raise _error(path, f"entry {name!r}: value outside supported 32-bit integer range")
    since, deprecated = _versions(element, version, path)
    return {"name": name, "value": value, "since": since, "deprecated_since": deprecated,
            "description": _description(element)}


def _enumeration(element: ET.Element, version: int, path: str) -> dict[str, Any]:
    children = _children(element, {"entry"}, path)
    name = _name(element, path, suffix=True)
    since = _positive(element, "since", path, 1)
    if since > version:
        raise _error(path, f"enum {name!r}: since exceeds interface version")
    bitfield = _bool(element, "bitfield", path)
    if not children:
        raise _error(path, f"enum {name!r}: empty enumerations are unsupported")
    entries: dict[str, Any] = {}
    for child in children:
        entry = _entry(child, version, bitfield, path)
        if entry["name"] in entries:
            raise _error(path, f"enum {name!r}: duplicate entry {entry['name']!r}")
        entries[entry["name"]] = entry
    values = [entry["value"] for entry in entries.values()]
    if not bitfield and any(value < 0 for value in values) and any(value > 2**31 - 1 for value in values):
        raise _error(path, f"enum {name!r}: values must fit one signed or unsigned 32-bit integer domain")
    return {"name": name, "since": since, "bitfield": bitfield,
            "description": _description(element), "entries": entries}


def _interface(element: ET.Element, path: str) -> dict[str, Any]:
    children = _children(element, {"request", "event", "enum"}, path)
    name = _name(element, path)
    version = _positive(element, "version", path)
    frozen = _bool(element, "frozen", path)
    if frozen and version != 1:
        raise _error(path, f"interface {name!r}: frozen interfaces must have version 1")
    if not children:
        raise _error(path, f"interface {name!r}: expected at least one request, event, or enum")
    requests: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    enums: dict[str, Any] = {}
    names: set[str] = set()
    for child in children:
        if child.tag == "enum":
            enum = _enumeration(child, version, path)
            if enum["name"] in enums:
                raise _error(path, f"interface {name!r}: duplicate enum {enum['name']!r}")
            enums[enum["name"]] = enum
        else:
            messages = requests if child.tag == "request" else events
            message = _message(child, len(messages), version, path)
            if message["name"] in names:
                raise _error(path, f"interface {name!r}: duplicate request/event name {message['name']!r}")
            names.add(message["name"])
            messages.append(message)
    return {"name": name, "version": version, "frozen": frozen,
            "description": _description(element), "requests": requests, "events": events, "enums": enums}


def _verify_enum_types(interfaces: dict[str, Any]) -> None:
    for iface in interfaces.values():
        for message in iface["requests"] + iface["events"]:
            for arg in message["args"]:
                reference = arg["enum"]
                if reference is None:
                    continue
                if "." in reference:
                    interface_name, enum_name = reference.split(".", 1)
                else:
                    interface_name, enum_name = iface["name"], reference
                if interface_name in interfaces and enum_name not in interfaces[interface_name]["enums"]:
                    raise InputError(f"{iface['source']}: {iface['name']}.{message['name']}.{arg['name']}: supplied interface {interface_name!r} has no enum {enum_name!r}")
                target = interfaces.get(interface_name, {}).get("enums", {}).get(enum_name)
                if target and target["bitfield"] and arg["type"] != "uint":
                    raise InputError(f"{iface['name']}.{message['name']}.{arg['name']}: bitfield enum references require uint")


def load_snapshot(path: Path) -> dict[str, Any]:
    """Load one file or a recursive XML tree into a normalized snapshot.

    Source hashes cover the original bytes. Paths are the basename for a file,
    or POSIX-style paths relative to the supplied directory. XML comments and
    presentation whitespace do not affect the normalized contract.
    """
    path = Path(path)
    interfaces: dict[str, Any] = {}
    protocols: dict[str, str] = {}
    sources: list[dict[str, str]] = []
    total_bytes = 0
    for file, relative in _files(path):
        data = _read(file, relative)
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_BYTES:
            raise _error(relative, f"snapshot exceeds {MAX_TOTAL_BYTES} bytes")
        root = _tree(data, relative)
        name = _name(root, relative)
        if name in protocols:
            raise _error(relative, f"duplicate protocol name {name!r}")
        # DTD order: copyright?, description?, interface+.
        children = list(root)
        index = 0
        if children and children[0].tag == "copyright":
            if list(children[0]):
                raise _error(relative, "copyright cannot contain XML elements")
            index += 1
        if len(children) > index and children[index].tag == "description":
            if list(children[index]):
                raise _error(relative, "description cannot contain XML elements")
            index += 1
        definitions = children[index:]
        if not definitions or any(child.tag != "interface" for child in definitions):
            raise _error(relative, "protocol must contain copyright?, description?, then one or more interfaces")
        protocols[name] = _description(root)
        for child in definitions:
            iface = _interface(child, relative)
            iface["protocol"] = name
            iface["source"] = relative
            if iface["name"] in interfaces:
                raise _error(relative, f"duplicate interface name {iface['name']!r}")
            interfaces[iface["name"]] = iface
        sources.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest()})
    _verify_enum_types(interfaces)
    return {"interfaces": interfaces, "protocols": protocols, "sources": sources}
