# Positioning and whole-product boundary

Date: **2026-10-15**. The following is a constructed product strategy for an
open-source tool. It is not evidence of customers, endorsements, distribution
traction, or financial outcomes.

## Two-sentence positioning statement

For maintainers of Wayland extension XML who are dissatisfied with reconstructing
opcode and version changes by hand during revision review, wl-contract is an
offline protocol-contract comparison tool that identifies structural changes to
an existing interface before bindings are regenerated.
Unlike a workflow built from a scanner, raw diffs, and a C/C++ ABI checker,
wl-contract compares the XML revisions directly and supplies a repeatable
human-readable or machine-readable report, explicit failures for unsupported
input, examples, tests, and installation documentation for that bounded job.

## Beachhead and reason to use it

The beachhead is a maintainer reviewing a change to a single Wayland extension
that preserves an existing interface identity. They already have the published
definition and proposed replacement locally and need evidence for a pull/merge
request review. This is narrower than all desktop developers, all protocol
authors, or all applications that happen to use Wayland.

The reason to use the product is to expose structural contract drift at the
moment a revision is reviewed. The research shows the failure mechanism and
specific maintainer examples; adoption demand remains an inference.
[Research and alternatives](research.md).

The **market alternative** is the current process: an expert reads XML and
generated-code diffs, reconstructs the protocol implications, and relies on
existing build and runtime tests. The **product alternative** is an assembled
tool workflow using `wayland-scanner`, Git, and where appropriate a header-aware
C/C++ ABI checker. These are capable tools. wl-contract's distinction is the
direct old/new Wayland contract interpretation and repeatable report, with no
compiler or display server required for the comparison.

## Constructed usage scenario

This scenario is illustrative and has not been observed as a customer deployment.

A compositor project's protocol maintainer receives a proposed XML revision
that inserts a request above an existing request. Both files are valid input to
a scanner, and generated code still compiles. The maintainer compares the
released and proposed definitions with wl-contract, sees which existing opcode
assignments changed, and asks for an append-only revision or a deliberately new
interface identity. They rerun the comparison, inspect the ordinary diff for
normative behavior changes, and run their native build and interoperability
tests before accepting the change. The tool supplies evidence for that decision;
it cannot make the protocol-design decision on the maintainer's behalf.

## Whole product for this job

For this scope, completeness means that a maintainer can install a published
artifact, compare local files without a network connection, understand the
report and exit status, reproduce an example, and distinguish a structural
finding from a validation/input failure. The package needs documented supported
syntax, safe parser limits, deterministic output, meaningful acceptance tests,
and explicit semantic limitations. Existing scanners, code review, and runtime
tests complete the surrounding engineering workflow.

A pass means that the supported comparison detected no structural violations;
it is not a proof of behavioral compatibility. The product must not quietly
accept unknown syntax or incomplete parsing. A GUI, hosted account, registry
service, generalized schema framework, and automatic protocol rewriting are not
needed to complete this particular job.

## How Moore's concepts were applied

Geoffrey Moore's original positioning handout frames positioning as a short
statement connecting one audience, its reason to act, a familiar category, a key
benefit, and the basis for preferring it to an alternative. We apply that by
leading with revision review for an extension maintainer and direct contract
interpretation, rather than listing unrelated uses or claiming uniqueness.
[Moore, positioning handout, pages 15-20](https://web.stanford.edu/group/e145/cgi-bin/winter/drupal/upload/handouts/MoorePositioning.pdf).

Chasm Group's whole-product guidance recommends the least complex complete
solution to the selected customer's problem and reducing friction in
installation and use. We apply that to installation, offline operation,
actionable output, examples, failure behavior, and review evidence within a
small explicit scope. We do not infer a revenue plan, market-share target, or
reference customers from a business framework for this open-source project.
[Chasm Group, whole-product guidance](https://chasmgroup.com/7-deadly-sins-how-to-successfully-cross-the-chasm-with-cloud-based-solutions-by-avoiding-these-mistakes/).
