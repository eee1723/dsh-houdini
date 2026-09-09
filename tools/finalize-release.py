"""Sign an unsigned assembly in an isolated signing environment; never execute its code."""
import argparse
from pathlib import Path
import shutil
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_builder", ROOT / "tools/build-release.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--directory", type=Path, required=True)
parser.add_argument("--key-id", required=True)
parser.add_argument("--trust", type=Path, default=ROOT / "installer/release-trust.json")
parser.add_argument("--candidate", action="store_true")
args = parser.parse_args()
node = shutil.which("node")
if not node:
    raise RuntimeError("The signing environment requires a trusted Node installation")
builder.finalize(args.directory.resolve(), args.trust, args.key_id, node, candidate=args.candidate)
