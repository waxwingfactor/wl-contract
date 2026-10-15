# Public release verification: v1.0.0

Verified on 2026-10-15. This is observed public-artifact testing, separate from
local development tests and configured CI. The released package does not have
production deployments, reference customers, or a runtime-interoperability
certification claim.

## Exact source, review and checks

- [Public release](https://github.com/waxwingfactor/wl-contract/releases/tag/v1.0.0)
- Source/tag commit: `3eac47707b692cfff170be6cfa586ef7633425e1`
- [Implementation PR and independent AI-review records](https://github.com/waxwingfactor/wl-contract/pull/2)
- [Required PR CI](https://github.com/waxwingfactor/wl-contract/actions/runs/38794636931)
- [Passing CI on the exact merged release commit](https://github.com/waxwingfactor/wl-contract/actions/runs/38794852105)

Both CI runs passed on Linux, macOS and Windows with Python 3.9 and 3.14. Each job
built/installed a wheel, ran the 86-test suite, and built/installed the source
distribution in a separate environment. Windows executed 83 tests and skipped
three OS-inapplicable tests (FIFO and control-character filenames); the other
four jobs executed all 86. The enforced `gate` passed before merge. Administrator
enforcement and required checks were retained.

Independent reviews were performed by separate AI agents and recorded honestly
in the PR. They are not human approvals or a second GitHub account. A reproduced
terminal-control injection was fixed and regression-tested before release. The
first Windows run caught an expected-hash test using LF memory text instead of
actual CRLF file bytes; the test was corrected with an explicit LF/CRLF regression.
The original failed run remains visible in CI history.

## Published artifact identity

| Artifact | SHA-256 |
| --- | --- |
| `wl_contract-1.0.0-py3-none-any.whl` | `5a683a8b5bf00870ceea76f7c98d3a1b04582afc9eaec2080df72e96ad76a101` |
| `wl_contract-1.0.0.tar.gz` | `90dee1f28c1b066789f58a209905d66dafb60de085f813f0eb81a7f26c722183` |
| `PROVENANCE.json` | `cad0c460c9cbfc615c5684b8bc621dbb97883cb69711e2960d6e5f2ed26e7e57` |

Wheel/sdist were built from a clean Git archive of the exact merged commit.
`PROVENANCE.json` records the source module hashes, artifact hashes, build
environment and CI/review references. `SHA256SUMS`, GitHub release-asset digests
and actual downloaded bytes agree. Every packaged Python module matches its
provenance source hash in both distributions. No signing, attestation or
byte-reproducible-build claim is made. Assets were not replaced after verification.

## Actual public download and installation results

The lead verifier fetched release metadata and all four release assets over
anonymous HTTP, receiving status 200, into a directory outside the development
checkout. On macOS/Darwin 25.5.0 arm64 with CPython 3.9.6, it installed the actual
downloaded wheel and sdist into two separate fresh virtual environments. No
editable installation, user site or PYTHONPATH was used. Module locations were
checked to be inside the new environments. Source builds used free build
dependencies; installed runtime operation needs no dependencies or network.

For **each** installed artifact:

- All 86 tests from the downloaded source distribution passed using isolated
  Python and installed-package mode, including the real upstream enum regression.
- Unchanged XML returned exit 0 / `no_structural_hazards`.
- Inserted-request XML returned exit 1 / `incompatible`.
- Valid since-gated append returned exit 3 / `needs_review`.
- DTD-bearing input returned exit 2 / JSON `invalid` on stderr, with no result on
  stdout.

The wheel then ran successfully after all extracted source, tests and docs were
deleted, input files moved to a new directory, and Python socket creation blocked.
This verifies installed-package independence and relevant offline/relocated-input
operation; relocation of an entire virtual environment is not claimed.

The public-wheel installation also compared all **66** XML files individually to
themselves at upstream wayland-protocols commit
`819004adb3ab7e46f3fa3caef05b96e20434b244`, with no unsupported files or unexpected
findings. [Per-file hashes and results](evidence/v1.0.0/corpus.json). This is parser
coverage, not a test of every historical transition. The actual historical
`ext-background-effect` correction produces exactly one finding: `blur` changes
from numeric 0 to 1. Its original author explained that the old capability was
already unusable; this does not establish that the correction broke working clients.

[Lead machine-readable observations](evidence/v1.0.0/lead.json).
The [public verification harness](../tools/verify_public_release.py) repeats the
lead checks in a new output directory; it downloads and installs the release.
It is a verification tool for this exact release, not part of the installed CLI.

## Independent public repetition

A separate AI agent wrote and ran its own verifier, using anonymous Python
urllib downloads rather than the lead's curl harness. It resolved the public
annotated tag to the expected commit, checked all four GitHub asset digests,
the checksum manifest, provenance fields and packaged/installed module bytes.
It installed wheel and sdist noneditably in two additional fresh environments.
Each passed all 86 tests and `pip check`.

After deleting the extracted source and moving the five example/historical input
files, it verified both environment import locations, all four exit paths, and
the actual historical `blur` change. Instrumented Python socket connection,
DNS and urllib calls recorded zero networking attempts during those runtime
workflows. This is Python-level instrumentation, not an OS firewall guarantee.
All 23 recorded commands/checks passed. The environment was macOS arm64 with
CPython 3.9.6; this independent run is not an additional OS test matrix.

[Independent observations, command results and digests](evidence/v1.0.0/independent.json)
and its [separately authored harness](../tools/verify_public_release_independent.py)
are public. To repeat the two checks in separate new output directories:

```sh
python tools/verify_public_release.py /tmp/wl-contract-lead-repeat
python tools/verify_public_release_independent.py \
  --expected-commit 3eac47707b692cfff170be6cfa586ef7633425e1 \
  --root /tmp/wl-contract-independent-repeat
```

The lead harness requires Python 3.9+, curl and a POSIX host. The independent
harness also supports Windows paths. Both intentionally install the published
software and source-build tooling into fresh environments. The product CLI's
cross-platform support is tested by CI; these verification helpers are outside
the installed package.

## Limits

These checks establish the reported installation/workflow behavior for the exact
artifacts and environments above. They do not prove interoperability with a real
compositor, correctness of normative prose, generated-language ABI compatibility,
or definitions outside the supplied inputs. Future upstream XML dialects may be
rejected until explicitly supported. Research demand remains inferred from
documented problems; no adoption or measured-savings claim is made.
