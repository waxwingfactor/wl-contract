# Supported contract, version 1

## Workflow and compatibility

Start with a released XML definition and proposed replacement. Compare them,
retain the report with the review, correct detected structural hazards, inspect
normative prose, regenerate bindings with native tools, and run the project's
build and runtime tests. No protocol files are rewritten. A new major interface
identity is reported as removal/addition so intentional breaks remain visible.

The CLI is supported on CPython 3.9 through 3.14 on Linux, macOS and Windows.
Runtime has no third-party dependencies or network access. The library modules
are internal implementation details. Future report-schema changes require a new
`schema_version`; consumers should ignore new finding codes they do not know
while honoring severity and verdict.

## Inputs and bounds

`wl-contract compare OLD NEW [--format text|json] [--output NEW_REPORT]`

Each side accepts one regular UTF-8 XML file (optional UTF-8 BOM), or a local
directory scanned recursively for lowercase `*.xml`. Non-XML regular files are
ignored. All symlinks and non-regular entries in a directory input are rejected,
including entries that would otherwise be ignored. A directory with no XML is
invalid. Duplicate protocol names or interface names within a snapshot are
invalid; file ordering never chooses a winner. Supply coherent, quiescent
snapshots, not a concurrently changing checkout. The tool does not provide an
OS sandbox or protection against a process replacing parent directories during
inspection. User-chosen parent directories and output locations are trusted.

| Limit | Per snapshot/file |
| --- | --- |
| XML size | 4 MiB per file, 32 MiB aggregate |
| XML files | 256 per snapshot |
| Filesystem entries | 4,096 per directory snapshot, including ignored entries |
| Filesystem/XML depth | 16 directory levels / 16 XML element levels |
| XML elements | 50,000 per file |
| Interface versions | Positive decimal integer, at most 2,147,483,647 |
| Message arguments | At most 20 declared and 20 expanded wire arguments, and one `new_id` |

No archives, URLs, stdin, arbitrary schemas or executable configuration are
accepted. DOCTYPE/ENTITY declarations, namespaces, unknown elements/attributes,
unexpected element nesting, duplicate members and invalid values fail with exit
2. A declaration naming another encoding is rejected even for ASCII content.
DTD/entity declaration-like text in a comment is also conservatively rejected.
XML processing instructions and comments are ignored; they must not carry
normative contract information.

Supported vocabulary follows the
[current upstream DTD](https://github.com/wayland-mirror/wayland/blob/1bd29e0709db70b6463c947f150ea20dcfce9cac/protocol/wayland.dtd):
protocol, copyright, description, interface, request, event, arg, enum, entry;
`frozen`, `deprecated-since`, `allow-null`, `interface`, and `enum` attributes are
included. A description requires a summary, as the DTD and native scanner do.
Empty interfaces/enumerations are explicitly unsupported. Protocol and interface
names use ASCII identifiers; enum/entry names also permit a leading digit.
`destroy` messages require destructor type, matching the scanner's restriction.

Enum decimal, hexadecimal and legacy octal values normalize numerically.
Bitfields are unsigned 32-bit. A regular enumeration must fit either signed
32-bit or unsigned 32-bit values consistently. `since` defaults to 1; it must
not exceed the containing interface version. Deprecation must be later than
`since` and no later than the interface maximum. Enum and entry `since` values
are independently interpreted. Nullable arguments are strings/objects only.
Generic `new_id` is allowed in requests; events require a typed target.

Named external interface targets are retained as opaque contract identities;
they are not fetched. Missing enums in supplied interfaces are invalid. Enum
references into absent interfaces are explicitly outside coverage. The parser
checks supported declarations; it is not a replacement for a particular
language generator, DTD engine or all scanner warnings.

## Comparison rules and coverage

- Requests and events have separate, zero-based opcode sequences. Existing
  positions, expanded wire types, interface targets, nullability, `since`, and
  destructor status are compared. A moved existing message is a break even when
  its new neighbor has an identical argument layout.
- A new tail message must have `since` greater than the old interface maximum
  and no greater than the new maximum. Valid appends require human review.
  Frozen interfaces stay at version 1 and cannot gain messages.
- Generic `new_id` expands to `string`, `uint`, `new_id` (`sun`); a typed creation
  uses `n`. Findings show these expanded signatures where layout changes.
- Existing interface versions cannot decrease. For typed constructors whose
  target is supplied in both snapshots, a target version increase requires
  parent propagation reaching that version. Registry globals, unsupplied parents,
  runtime factories and ancestry not expressed by typed `new_id` are not inferred.
- Existing enum values, member availability, bitfield interpretation and removal
  are checked. Entry ordering and equivalent numeric spellings are neutral.
  New enum values/annotations require review: an enum annotation alone does not
  restrict legal wire values.
- Names at a retained opcode, argument names, deprecation, protocol-container
  changes and normalized descriptions/summaries require review. A rename can
  preserve wire layout but affect generated APIs. Added/removed interfaces stay
  visible. Copyright-only, comments and presentation-whitespace changes are
  neutral. Whitespace in prose is normalized; inspect the raw diff when layout
  itself matters.

The policy is deliberately conservative and direction-independent. Any change
in an existing nullability contract is reported as a break even if a particular
client/server deployment can safely tolerate that direction of change. A break
is a review finding, not proof that a real deployed client malfunctioned.

## Output and failure behavior

Text is the default. JSON is deterministic for the same inputs and tool version:
no timestamps, absolute source paths, machine identifiers or random IDs. Source
paths are a file's basename or a POSIX-style directory-relative name. Each source
record includes SHA-256 of its original bytes. Findings use stable semantic
paths such as `interface/example_v1/request/0:set/arg/0`, severity, a code,
old/new values and an explanation. Paths identify declarations rather than XML
line numbers, so reformatting does not change finding identity.

`limits.behavior_certified` is always false and
`limits.external_interfaces_not_checked` lists referenced absent interfaces.
No finding means only that the implemented checks found no hazard in the
supplied declarations. It does not establish semantic or runtime compatibility.

Exit codes are 0 for no supported hazard, 1 for a structural break, 3 for review
without a break, and 2 for input/I/O/unsupported failures. Breaks take precedence
over review findings; all findings remain in the report. Comparison results,
including exit 1/3, go to stdout or the new output file. Input/I/O errors go only
to stderr, in JSON with `verdict: invalid` when JSON was requested. Argument
syntax errors use argparse's ordinary stderr format and exit 2.

`--output` uses a temporary file in the destination directory, fsync, then atomic
hard-link publication. Existing paths, including symlinks and either input, are
never overwritten. Filesystems without hard-link support fail safely with exit
2. The output parent must already exist. On an error, no comparison report is
published; a preexisting file stays untouched. Stdout streaming cannot be
transactional and its consumer is responsible for checking the exit code.
