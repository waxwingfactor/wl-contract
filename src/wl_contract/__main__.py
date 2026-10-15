"""Command-line interface. Runtime inputs are local and never executed."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from . import __version__
from .compare import compare_snapshots
from .parser import InputError, load_snapshot


def text_report(report):
    lines = ["wl-contract " + report["tool_version"] + ": " + report["verdict"],
             "Behavior is not certified. Review normative prose and runtime implementations."]
    for finding in report["findings"]:
        lines.extend(["", finding["severity"].upper() + " " + finding["code"] + " " + finding["path"],
                      "  " + finding["message"],
                      "  old: " + json.dumps(finding["old"], ensure_ascii=True, sort_keys=True),
                      "  new: " + json.dumps(finding["new"], ensure_ascii=True, sort_keys=True)])
    external = report["limits"]["external_interfaces_not_checked"]
    if external:
        lines.append("\nExternal interfaces not checked: " + ", ".join(external))
    for side in ("old", "new"):
        for source in report[side]["sources"]:
            lines.append(side + " sha256 " + source["sha256"] + " "
                         + json.dumps(source["path"], ensure_ascii=True))
    return "\n".join(lines) + "\n"


def write_report(path, content):
    """Publish atomically without overwriting an existing report or input."""
    parent = path.parent
    descriptor, temporary = tempfile.mkstemp(prefix=".wl-contract-", dir=str(parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link creation is an atomic no-clobber publish on supported local
        # filesystems. If unavailable, fail safely; never fall back to overwrite.
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline structural review of two Wayland XML revisions.")
    parser.add_argument("--version", action="version", version="wl-contract " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("compare", help="compare an old and new local XML file or XML directory tree")
    command.add_argument("old", type=Path)
    command.add_argument("new", type=Path)
    command.add_argument("--format", choices=("text", "json"), default="text")
    command.add_argument("--output", type=Path, help="new report file; existing paths are never overwritten")
    args = parser.parse_args(argv)
    try:
        old, new = load_snapshot(args.old), load_snapshot(args.new)
        report = compare_snapshots(old, new)
        content = (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
                   if args.format == "json" else text_report(report))
        if args.output:
            write_report(args.output, content)
        else:
            sys.stdout.write(content)
        return {"no_structural_hazards": 0, "incompatible": 1, "needs_review": 3}[report["verdict"]]
    except (InputError, OSError, UnicodeError) as error:
        message = str(error)
        if args.format == "json":
            sys.stderr.write(json.dumps({"schema_version": 1, "verdict": "invalid", "error": message},
                                        ensure_ascii=True) + "\n")
        else:
            sys.stderr.write("wl-contract: " + json.dumps(message, ensure_ascii=True) + "\n")
        return 2
    except BrokenPipeError:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
