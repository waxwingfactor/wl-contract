"""Verify source contents and exercise the built sdist outside the checkout."""
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import venv

root = Path(__file__).resolve().parents[1]
sdists = list((root / "dist").glob("*.tar.gz"))
if len(sdists) != 1:
    raise SystemExit("expected exactly one source distribution")
with tempfile.TemporaryDirectory(prefix="wl-contract-sdist-") as scratch:
    base = Path(scratch).resolve()
    with tarfile.open(sdists[0]) as archive:
        members = archive.getmembers()
        for member in members:
            if not member.isfile() and not member.isdir():
                raise SystemExit("unexpected non-regular distribution member")
            target = (base / member.name).resolve()
            if base not in target.parents:
                raise SystemExit("unexpected archive traversal")
        archive.extractall(base)
    source = next(p for p in base.iterdir() if p.is_dir())
    for relative in ("README.md", "LICENSE", "docs/research.md", "docs/contract.md",
                     "examples/baseline.xml", "tests/test_acceptance.py"):
        if not (source / relative).is_file():
            raise SystemExit("sdist missing " + relative)
    envdir = base / "isolated"
    venv.EnvBuilder(with_pip=True).create(envdir)
    bindir = envdir / ("Scripts" if os.name == "nt" else "bin")
    python = bindir / ("python.exe" if os.name == "nt" else "python")
    clean = os.environ.copy()
    clean.pop("PYTHONPATH", None)
    clean["PYTHONNOUSERSITE"] = "1"
    clean["PIP_NO_CACHE_DIR"] = "1"
    clean["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    subprocess.run([str(python), "-m", "pip", "install", "--no-deps", str(sdists[0])],
                   cwd=base, env=clean, check=True)
    result = subprocess.run([str(python), "-I", "-m", "wl_contract", "compare",
                             str(source / "examples/baseline.xml"),
                             str(source / "examples/broken.xml"), "--format", "json"],
                            cwd=base, env=clean, capture_output=True, text=True, check=False)
    if result.returncode != 1 or '"verdict": "incompatible"' not in result.stdout:
        raise SystemExit("sdist-installed CLI failed: " + result.stdout + result.stderr)
print("sdist includes docs/examples/tests, installs in an isolated venv, and detects the example break")
