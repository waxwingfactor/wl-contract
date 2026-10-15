# wl-contract

Review **two Wayland protocol XML revisions** before regenerating bindings.
wl-contract identifies opcode drift, wire-layout changes, changed enum values,
lifetime contracts and versioning hazards. It retains prose/API changes as
explicit human-review findings.

It runs offline with Python 3.9–3.14 and no runtime dependencies, compiler,
compositor, service or account. The supported interface is the CLI.

## Install

Download a wheel and `SHA256SUMS` from the [release](https://github.com/waxwingfactor/wl-contract/releases/latest),
verify its SHA-256 against the published manifest, then install it:

```sh
python -m pip install ./wl_contract-1.0.0-py3-none-any.whl
wl-contract --version
```

For an offline machine, copy the verified wheel and use
`python -m pip install --no-index ./wl_contract-1.0.0-py3-none-any.whl`.
The source distribution contains documentation, examples and tests. Building
from source requires setuptools >=77 and wheel; `python -m build` also needs the
`build` frontend. There is no PyPI publication claim.

## Review a revision

```sh
wl-contract compare released.xml proposed.xml
wl-contract compare old-protocols/ new-protocols/ --format json --output review.json
```

Inputs may be a single XML file or a directory of complementary `*.xml` files.
Each side must have unique protocol and interface names. For a repository with
several historical variants of an interface, select the intended files separately.
Directory-relative paths and exact source hashes make the report reproducible.
Existing report paths are never overwritten.

| Exit | Verdict | Next action |
| --- | --- | --- |
| 0 | `no_structural_hazards` | No supported structural hazards detected; still review semantics and run native/runtime tests. |
| 1 | `incompatible` | Existing structural contract changed or a version rule failed. Inspect findings; preserve the old contract or introduce a deliberate new major identity. |
| 2 | Invalid/unsupported input or I/O failure | Correct the input or environment; no partial report is published. |
| 3 | `needs_review` | Prose, API identity, new features, or annotations need human judgment; no structural break was detected. |

An interface-version bump alone does not repair a reordered opcode. A
since-gated append produces exit 3 because new behavior still needs review.
The tool never declares behavioral compatibility.

## Try the included examples

Unpack the source distribution and, from its directory, run:

```sh
wl-contract compare examples/baseline.xml examples/baseline.xml  # exit 0
wl-contract compare examples/baseline.xml examples/broken.xml    # exit 1: inserted request
wl-contract compare examples/baseline.xml examples/extended.xml  # exit 3: version-gated append
```

These are constructed examples, not deployments. JSON reports have
`schema_version: 1`, a verdict, findings with old/new values, input SHA-256 hashes,
and explicit coverage limits. Errors go to stderr (JSON when requested).

## Supported boundary

The current Wayland XML vocabulary is supported within strict resource limits.
Unknown syntax, ambiguous duplicate identities, non-UTF-8 files, DTDs/entities,
symlinks and non-regular input files fail clearly. Named external interfaces are
reported as unchecked unless their definitions are supplied. Inputs must be
stable local snapshots; concurrent changes to directory trees are unsupported.

The comparison complements `wayland-scanner --strict`, generated-header review,
and runtime interoperability tests. It does not certify state machines, driver
behavior, advertised globals, generated-language ABI, or protocol definitions
that were not supplied. Read the [complete input/output contract](docs/contract.md).

## Evidence and maintenance

- [Dated research and feature-level alternatives](docs/research.md)
- [Beachhead, constructed scenario and positioning](docs/positioning.md)
- [Release and contribution process](docs/maintenance.md)
- [Published validation evidence](https://github.com/waxwingfactor/wl-contract/releases/latest)

```sh
python -m pip install build
python -m build
python tests/install_wheel.py
WL_CONTRACT_TEST_INSTALLED=1 python -m unittest discover -s tests -v
python tests/check_distribution.py
```

CI tests installed distributions on Linux, macOS and Windows with Python 3.9 and
3.14. Release records identify observed results; a configured matrix alone is
not proof it passed. MIT licensed. Maintainer support is through GitHub issues;
there is no commercial SLA or reference-customer claim.
