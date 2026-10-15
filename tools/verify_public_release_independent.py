#!/usr/bin/env python3
"""Independent anonymous-download release checks; never imports the checkout."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import venv
import zipfile


REPOSITORY = "waxwingfactor/wl-contract"
TAG = "v1.0.0"
NETWORK_DENIED_RUNNER = r'''
import runpy, socket, sys, urllib.request
attempts = []
def denied(*args, **kwargs):
    attempts.append(True)
    raise OSError("Network disabled by independent verifier")
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
socket.getaddrinfo = denied
urllib.request.urlopen = denied
sys.argv = ["wl-contract"] + sys.argv[1:]
try:
    runpy.run_module("wl_contract", run_name="__main__")
except SystemExit as error:
    code = error.code or 0
else:
    code = 0
if attempts:
    print("Unexpected networking attempt", file=sys.stderr)
    raise SystemExit(99)
raise SystemExit(code)
'''


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "wl-contract-independent-release-verifier",
                      "Accept": "application/vnd.github+json"},
    )
    # Deliberately no Authorization header or gh credential use.
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def json_fetch(url):
    return json.loads(fetch(url))


def extract_source(archive, destination):
    seen = set()
    total = 0
    destination.mkdir()
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                raise AssertionError("Unsafe source archive path")
            normalized = path.as_posix().rstrip("/")
            if normalized in seen:
                raise AssertionError("Duplicate source archive path")
            seen.add(normalized)
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                total += member.size
                if member.size > 16 * 1024 * 1024 or total > 100 * 1024 * 1024:
                    raise AssertionError("Source archive exceeds verifier bounds")
                target.parent.mkdir(parents=True, exist_ok=True)
                reader = stream.extractfile(member)
                if reader is None:
                    raise AssertionError("Unreadable source archive member")
                with reader:
                    target.write_bytes(reader.read())
            else:
                raise AssertionError("Source archive contains a non-regular member")
    projects = list(destination.glob("*/pyproject.toml"))
    if len(projects) != 1:
        raise AssertionError("Expected one source project root")
    return projects[0].parent


class Verifier:
    def __init__(self, root, expected_commit):
        self.root = root.resolve()
        self.expected_commit = expected_commit
        self.root.mkdir(parents=True, exist_ok=False)
        self.downloads = self.root / "downloads"
        self.downloads.mkdir()
        self.report = {
            "schema_version": 1,
            "verifier": "independent AI-agent public artifact verification",
            "repository": "https://github.com/" + REPOSITORY,
            "release": "https://github.com/" + REPOSITORY + "/releases/tag/" + TAG,
            "expected_source_commit": expected_commit,
            "anonymous_downloads": True,
            "environment": {"python": platform.python_version(),
                            "platform": platform.platform(),
                            "system": platform.system(), "machine": platform.machine()},
            "artifacts": [], "checks": [], "status": "running",
        }
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("PIP_") and key not in {
                        "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV"}}
        self.env.update({"PYTHONNOUSERSITE": "1", "PIP_CONFIG_FILE": os.devnull,
                         "WL_CONTRACT_TEST_INSTALLED": "1"})

    def scrub(self, value):
        if isinstance(value, dict):
            return {key: self.scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.scrub(item) for item in value]
        if isinstance(value, str):
            value = value.replace(str(self.root), "<verification-root>")
            value = re.sub(r"/Users/[^/\s]+", "/USER", value)
            return value
        return value

    def save(self):
        report_path = self.root / "independent-public-verification.json"
        report_path.write_text(json.dumps(self.scrub(self.report), sort_keys=True,
                                         indent=2) + "\n", encoding="utf-8")

    def command(self, name, args, expected=0, cwd=None):
        result = subprocess.run([str(arg) for arg in args],
                                cwd=str(cwd or self.root), env=self.env,
                                capture_output=True, text=True, timeout=180)
        self.report["checks"].append({"name": name, "command": [str(arg) for arg in args],
                                      "expected_exit": expected, "observed_exit": result.returncode,
                                      "stdout": result.stdout, "stderr": result.stderr,
                                      "passed": result.returncode == expected})
        self.save()
        if result.returncode != expected:
            raise AssertionError("Unexpected exit for " + name + ": " + str(result.returncode))
        print(name + ": passed", flush=True)
        return result

    def release_assets(self):
        api = "https://api.github.com/repos/" + REPOSITORY
        release = json_fetch(api + "/releases/tags/" + TAG)
        assert release["tag_name"] == TAG and not release["draft"]
        ref = json_fetch(api + "/git/ref/tags/" + TAG)["object"]
        for _ in range(4):
            if ref["type"] == "commit":
                break
            assert ref["type"] == "tag"
            ref = json_fetch(api + "/git/tags/" + ref["sha"])["object"]
        assert ref["type"] == "commit" and ref["sha"] == self.expected_commit
        self.report["tag_commit"] = ref["sha"]
        self.report["release_published_at"] = release["published_at"]
        assets = release["assets"]
        names = [asset["name"] for asset in assets]
        assert len(names) == len(set(names)), "Duplicate asset names"
        wheels = [name for name in names if name.endswith(".whl")]
        sources = [name for name in names if name.endswith(".tar.gz")]
        manifests = [name for name in names if name.upper() == "SHA256SUMS"]
        provenances = [name for name in names if "provenance" in name.lower() and name.endswith(".json")]
        assert len(wheels) == len(sources) == len(manifests) == len(provenances) == 1, names
        requested = set(wheels + sources + manifests + provenances)
        for asset in assets:
            name = asset["name"]
            if name not in requested:
                continue
            assert Path(name).name == name
            data = fetch(asset["browser_download_url"])
            digest = sha256(data)
            assert asset.get("digest") == "sha256:" + digest, "GitHub digest mismatch: " + name
            (self.downloads / name).write_bytes(data)
            self.report["artifacts"].append({"name": name, "sha256": digest,
                                             "size": len(data), "github_asset_id": asset["id"],
                                             "github_digest": asset["digest"],
                                             "url": asset["browser_download_url"]})
        manifest = (self.downloads / manifests[0]).read_text(encoding="utf-8")
        checksums = {}
        for line in manifest.splitlines():
            match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
            assert match, "Unsupported checksum manifest line"
            digest, name = match.groups()
            assert name not in checksums
            checksums[name] = digest.lower()
        for name in wheels + sources + provenances:
            assert checksums[name] == sha256((self.downloads / name).read_bytes())
        provenance = json.loads((self.downloads / provenances[0]).read_text(encoding="utf-8"))
        assert provenance["schema_version"] == 1
        assert provenance["source_repository"].rstrip("/").removesuffix(".git") == "https://github.com/" + REPOSITORY
        assert provenance["source_commit"] == self.expected_commit
        for name in wheels + sources:
            assert provenance["artifacts_sha256"][name] == sha256((self.downloads / name).read_bytes())
        matched = []
        def visit(value, path=()):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key.lower() in {"commit", "git_commit", "source_commit", "revision", "source_revision"} and child == self.expected_commit:
                        matched.append(".".join(path + (key,)))
                    visit(child, path + (key,))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, path + (str(index),))
        visit(provenance)
        assert matched, "Provenance lacks the exact expected source commit"
        self.report["provenance_commit_fields_verified"] = matched
        self.report["provenance"] = provenance
        self.report["checksum_manifest_verified"] = True
        self.report["github_asset_digests_verified"] = True
        self.save()
        print("Anonymous asset downloads, checksums, tag and provenance: passed", flush=True)
        return self.downloads / wheels[0], self.downloads / sources[0]

    def make_environment(self, name):
        root = self.root / (name + "-venv")
        venv.EnvBuilder(with_pip=True, clear=False).create(str(root))
        return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def verify(self):
        wheel, archive = self.release_assets()
        source = extract_source(archive, self.root / "extracted-sdist")
        for required in ("README.md", "LICENSE", "docs", "examples", "tests", "pyproject.toml"):
            assert (source / required).exists(), "Missing sdist payload: " + required
        test_sources = list((source / "tests").rglob("*.py"))
        assert test_sources
        source_digests = {path.relative_to(source).as_posix(): sha256(path.read_bytes())
                          for path in (source / "src/wl_contract").glob("*.py")}
        assert source_digests == self.report["provenance"]["source_modules_sha256"]
        with zipfile.ZipFile(wheel) as packaged:
            wheel_digests = {"src/" + name: sha256(packaged.read(name))
                             for name in packaged.namelist()
                             if name.startswith("wl_contract/") and name.endswith(".py")}
        assert source_digests == wheel_digests
        self.report["source_and_wheel_module_hashes_match_provenance"] = True
        self.report["sdist_payload_verified"] = True
        wheel_python = self.make_environment("wheel")
        sdist_python = self.make_environment("sdist")
        self.command("wheel installation", [wheel_python, "-I", "-m", "pip", "install", "--no-index", "--no-deps", wheel])
        self.command("sdist build dependencies", [sdist_python, "-I", "-m", "pip", "install", "--index-url", "https://pypi.org/simple", "--only-binary=:all:", "setuptools>=77", "wheel"])
        self.command("sdist noneditable installation", [sdist_python, "-I", "-m", "pip", "install", "--no-index", "--no-deps", "--no-build-isolation", archive])
        origin_check = r'''
import importlib.metadata, json, pathlib, sys, wl_contract
origin = pathlib.Path(wl_contract.__file__).resolve()
prefix = pathlib.Path(sys.prefix).resolve()
assert prefix in origin.parents, "Package escaped its clean venv"
assert importlib.metadata.version("wl-contract") == "1.0.0"
assert "src" not in origin.parts, "Source checkout import leakage"
print(json.dumps({"version": importlib.metadata.version("wl-contract"), "inside_clean_venv": True, "isolated": bool(sys.flags.isolated)}))
'''
        for name, interpreter in (("wheel", wheel_python), ("sdist", sdist_python)):
            self.command(name + " import origin", [interpreter, "-I", "-c", origin_check])
            suite = self.command(name + " bundled full suite", [interpreter, "-I", "-m", "unittest", "discover", "-s", source / "tests", "-v"])
            count = re.search(r"Ran (\d+) tests?", suite.stderr)
            assert count and int(count.group(1)) == 86, "Expected all 86 bundled tests"
            self.report.setdefault("installed_suite_test_counts", {})[name] = int(count.group(1))
            self.command(name + " dependency consistency", [interpreter, "-I", "-m", "pip", "check"])
        handoff = self.root / "temporary-input-location"
        handoff.mkdir()
        for path in (source / "examples").glob("*.xml"):
            shutil.copyfile(path, handoff / path.name)
        for path in (source / "tests/fixtures/upstream").glob("*.xml"):
            shutil.copyfile(path, handoff / path.name)
        assert len(list(handoff.glob("*.xml"))) >= 5
        input_hashes = {path.name: sha256(path.read_bytes()) for path in handoff.glob("*.xml")}
        relocated = self.root / "relocated-offline-inputs"
        handoff.rename(relocated)
        shutil.rmtree(self.root / "extracted-sdist")
        assert not source.exists() and not handoff.exists()
        self.report["extracted_source_removed_before_offline_workflow"] = True
        self.report["relocated_input_hashes"] = input_hashes
        historical_path = "interface/ext_background_effect_manager_v1/enum/capability/entry/blur"
        for name, interpreter in (("wheel", wheel_python), ("sdist", sdist_python)):
            self.command(name + " source-removed import origin", [interpreter, "-I", "-c", origin_check])
            cases = [
                ("unchanged", "baseline.xml", "baseline.xml", 0, "no_structural_hazards"),
                ("incompatible", "baseline.xml", "broken.xml", 1, "incompatible"),
                ("invalid", "does-not-exist.xml", "baseline.xml", 2, None),
                ("review", "baseline.xml", "extended.xml", 3, "needs_review"),
                ("real historical blur correction", "ext-background-effect.before.xml", "ext-background-effect.after.xml", 1, "incompatible"),
            ]
            for label, old, new, code, verdict in cases:
                result = self.command(name + " offline " + label,
                                      [interpreter, "-I", "-c", NETWORK_DENIED_RUNNER,
                                       "compare", relocated / old, relocated / new, "--format", "json"], expected=code)
                if verdict:
                    report = json.loads(result.stdout)
                    assert report["verdict"] == verdict
                    if "historical" in label:
                        assert any(item["severity"] == "break" and item["path"] == historical_path and item["old"] == 0 and item["new"] == 1 for item in report["findings"])
                else:
                    assert json.loads(result.stderr)["verdict"] == "invalid"
        assert input_hashes == {path.name: sha256(path.read_bytes()) for path in relocated.glob("*.xml")}
        self.report["network_attempts_during_offline_workflow"] = 0
        self.report["status"] = "passed"
        self.save()
        print("Independent public release verification PASSED", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    assert re.fullmatch(r"[0-9a-f]{40}", args.expected_commit)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = args.root or Path(__file__).resolve().parent / ("run-" + stamp)
    verifier = Verifier(root, args.expected_commit)
    try:
        verifier.verify()
    except Exception as error:
        verifier.report["status"] = "failed"
        verifier.report["failure"] = type(error).__name__ + ": " + str(error)
        verifier.save()
        raise


if __name__ == "__main__":
    main()
