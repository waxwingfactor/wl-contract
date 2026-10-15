# Opportunity and alternatives

Research date: **2026-10-15**. This is a bounded public-source assessment by AI
agents, not customer interviews, a market census, or evidence of adoption.

## Audience and supported job

The initial audience is maintainers who review revisions of a Wayland extension
XML file while preserving an existing interface name. They need to identify
changes to the published message contract before regenerating bindings or
accepting a contribution. The supported job starts with two local XML files and
ends with a reproducible structural comparison that can be read by a reviewer or
used by a local/CI check. Runtime client/compositor tests and review of normative
prose remain necessary.

This deliberately excludes generic dependency scanning, code linting, release
automation, and compositor implementation testing. The proposed value is the
interpretation of two protocol revisions using Wayland rules, rather than an
inventory of XML fields or another invocation of a scanner.

## Documented pain, and what it establishes

**Real downstream incompatibility.** The webOS Homebrew maintainers document
that vendor extension definitions differ across TV releases. Their guide
explains that inserted requests can shift opcodes without a corresponding
interface-version warning, and describes SDL-webOS's runtime workaround, which
obtains interface metadata from the device and matches requests by name. Their
protocol repository contains extracted TV/emulator definitions. This is concrete
evidence that source XML and version numbers alone can conceal a compatibility
problem. It does not establish that wl-contract can repair those devices or
replace their runtime workaround. [Maintainer guide](https://www.webosbrew.org/develop/guides/wayland/),
[extracted definitions](https://github.com/webosbrew/wayland-protocols).

**A structural contract mistake can survive normal development.** Upstream's
2025-06-25 change to `ext-background-effect-v1.xml` corrected the `blur`
capability value from zero to one after an enum became a bitfield. The author
explicitly describes this as technically breaking while explaining that the
capability had already been unusable, so clients could not receive it. This is
evidence of a reviewable enum-contract change, **not evidence of users being
broken by the correction**. [Upstream change and explanation](https://chromium.googlesource.com/external/anongit.freedesktop.org/git/wayland/wayland-protocols/+/efbc060534be948b63e1f395d69b583eebba3235).

**The rules are precise enough to automate a bounded part of review.** Wayland's
XML specification assigns request and event opcodes independently by declaration
order, requires additions at the end for backward compatibility, and uses the
order of arguments as their wire order. Interface versions and `since` determine
which messages exist at a bound version. These are structural checks with a
defined basis, rather than guesses about application behavior.
[Official XML language specification](https://wayland.freedesktop.org/docs/book/Message_XML.html).

**Demand is an inference.** These sources establish the failure mode and a
maintainer workflow. They support the hypothesis that a direct revision report
could be useful; they do not demonstrate willingness to adopt this particular
tool, measured time savings, a large market, or universal neglect.

## Three bounded challenge passes

The lead and two separately delegated agents performed the following checks
before implementation. These are three AI investigation passes; they are not
three human researchers or three independently commissioned market studies.

| Pass | Who and method | Finding and limit |
| --- | --- | --- |
| 1. Problem discovery | Lead AI agent: Wayland documentation, webOS maintainer evidence, and the upstream enum correction | A named maintainer audience has a real opcode/revision problem. The upstream correction is a useful historical example with the caveat above. |
| 2. Independent competition search | Separate discovery AI agent: searches including `Wayland protocol XML backwards compatibility checker`, `wayland protocol XML diff ABI checker`, `wayland protocol diff`, `wayland-lint protocol XML`, and `wayland protocol validator XML checker` | Results led to native scanners, generated bindings, protocol documentation, tracers, and general ABI tools. This search did not establish a direct equivalent; missing search results are not proof that none exists. |
| 3. Independent adversarial check | Separate adversary AI agent: fetched native `tests/meson.build`, `tests/scan.sh`, and `.gitlab-ci.yml`; independently searched competitors and the webOS maintainer evidence | Found `python-wayland --compare`, a materially closer alternative than a scanner. Its implementation inventories interface presence/version, leaving same-version opcode, argument, and enum changes outside that comparison. Native validation/code generation remains useful but supplies no old/new pair in the inspected test path. |

The discovery agent additionally checked source-level features of the native
and Rust scanners, Explorer, and ABI Compliance Checker, and fetched the
`python-wayland` comparison implementation after the adversary identified it.
A fourth rules agent checked the current DTD and scanner source at revision
`1bd29e0709db70b6463c947f150ea20dcfce9cac`. These checks challenged the scope;
they do not imply that an independent human approved the opportunity.

## Feature-level alternatives

| Alternative | What it does well | Remaining job for this audience |
| --- | --- | --- |
| Native `wayland-scanner` and upstream protocol tests | The C scanner validates a single definition in strict mode and emits client/server headers and marshalling code. The inspected protocol tests run all scanner output modes and compile generated C/C++ artifacts. These are valuable buildability checks. | The inspected scripts provide each current XML file as input, rather than an old/new pair; they do not report revision-level opcode or enum changes against a published baseline. |
| `python-wayland --compare` | Compares locally installed and latest official definitions, reporting interface version changes and interfaces present on only one side. Its changelog records the option in August 2024. This is a useful protocol-version inventory. | The inspected `compare_protocols()` reduces each interface to its version, then compares those maps. It does not compare request/event ordering, argument contracts, or enum values when an interface version stays unchanged, nor expose an explicit arbitrary local old/new file pair. |
| Smithay `wayland-scanner` | Generates Rust protocol bindings for the wayland-rs crates, avoiding manual binding maintenance. | Its documented purpose is generation from one protocol specification, rather than explaining a revision delta. |
| Wayland Explorer | Makes many protocols readable, links their sources, and provides access to protocol merge requests. It is a strong documentation aid. | Its stated workflow is reading generated protocol documentation, rather than enforcing an old/new structural contract locally or offline. |
| ABI Compliance Checker | Compares C/C++ library headers and shared objects. Its documented checks include changed enum values and macro constants, so generated-header analysis can catch some protocol-related changes. | Requires a C/C++ artifact/toolchain workflow and reasons about library API/ABI. It does not accept the Wayland XML pair directly or provide the protocol/version interpretation proposed here. |
| `git diff`, generated-header diffs, and expert review | Already available, flexible, and able to expose both code and normative prose changes. A careful expert can identify every change covered by this tool. | The reviewer must repeatedly reconstruct numeric opcodes, version constraints, and argument contracts. The proposed report makes that mechanical work explicit and repeatable while retaining prose review. |

Sources for the table: [C scanner usage](https://android.googlesource.com/platform/external/wayland/+/d31e1e5594a947a60707c09402a221e6ea8f2555/src/scanner.c),
[native test definition](https://github.com/wayland-mirror/wayland-protocols/blob/main/tests/meson.build),
[native scan script](https://github.com/wayland-mirror/wayland-protocols/blob/main/tests/scan.sh),
[python-wayland comparison implementation](https://git.sr.ht/~gk/python-wayland/blob/main/wayland/__main__.py),
[python-wayland changelog](https://python-wayland.org/changelog/),
[Smithay scanner](https://github.com/Smithay/wayland-rs/tree/master/wayland-scanner),
[Wayland Explorer](https://wayland.app/protocols/),
[ABI Compliance Checker](https://lvc.github.io/abi-compliance-checker/).
The native scripts were read directly from the mirror's `main` branch on the
research date; this statement is scoped to those inspected files, not every
upstream test or future revision.

Wayland's official model also states that generated inline protocol entry points
are outside the library ABI. Consequently a clean binary-library ABI comparison
alone is insufficient to establish protocol compatibility. This does not mean
header-aware ABI tools are ineffective: the table acknowledges the changes they
can detect. [Official protocol model](https://wayland.freedesktop.org/docs/book/Protocol.html).

## Selection and limits

The selected opportunity is **offline structural revision review for one
Wayland XML file or a coherent set of complementary definitions**. The compelling reason is a reviewable answer
to a narrow question: did this proposed definition alter the previously
published structural contract, and where?

The evidence supports a small, specific tool alongside existing scanners and
tests. It does not support claims that this is the first or only such tool, that
Wayland is broadly unreliable, or that a structural pass proves a compositor
and client remain interoperable. Names, descriptions, state machines, buffer
semantics, synchronization rules, and implementation bugs require judgment and
runtime tests. Unsupported input must fail clearly rather than produce an
optimistic partial result.

Research and positioning are release inputs, not release verification. See the
release's validation record for observed installation, artifact, and workflow
results.
