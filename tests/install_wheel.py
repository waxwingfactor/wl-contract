"""Install exactly the built wheel, never the checkout, in CI."""
from pathlib import Path
import subprocess
import sys

wheels = list(Path("dist").glob("*.whl"))
if len(wheels) != 1:
    raise SystemExit("expected exactly one built wheel")
subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--force-reinstall", str(wheels[0])], check=True)
