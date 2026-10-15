# Maintenance and release process

Use issues for scoped changes and a feature branch/pull request for implementation.
The single-maintainer repository requires the `gate` CI check on an up-to-date
branch before merging, including for administrators. It does not manufacture a
second GitHub identity or self-approval. Independent AI-agent review is recorded
explicitly as AI review in PR comments with findings, fixes and exact revisions.
It is not a human approval or a second account's GitHub review.

Tests run against built/installed wheels on Linux, macOS and Windows with the
lowest and highest claimed Python versions. An isolated environment also builds
and installs the source distribution, verifies included docs/examples/tests, and
exercises an actual CLI failure case. Required checks must pass before merging;
protections are not weakened to unblock a merge.

To release, build wheel and sdist from a clean exact merged revision, create
SHA-256 sums, tag the revision, publish assets, then download the actual public
assets outside the checkout. Verify hashes against both release assets and
GitHub asset digests, install each independently without editable installation
or PYTHONPATH, run supported and failure workflows, and test relocated/offline
wheel use. Record environments, revision, hashes and observed results in public
release evidence. A separate agent repeats public artifact installation and
checks. No public artifact is silently replaced after verification; a functional
fix requires a new version.

Report problems through GitHub issues with the tool version, exit code and a
small synthetic XML pair. Avoid publishing proprietary definitions or machine
paths. No telemetry is collected by the package. Security fixes follow the same
review/required-CI process. There is no service infrastructure or customer data
store to operate.
