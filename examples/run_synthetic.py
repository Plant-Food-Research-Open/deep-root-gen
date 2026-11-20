"""Run the same offline simulation API as the CLI, with explicit paths."""

import argparse
import json
from pathlib import Path

from deeprootgen.cli import simulate

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--config", type=Path, required=True)
parser.add_argument("--outdir", type=Path, required=True)
args = parser.parse_args()
print(json.dumps(simulate(json.loads(args.config.read_text()), args.outdir), indent=2))
