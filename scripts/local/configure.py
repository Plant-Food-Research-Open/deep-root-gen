"""Create a private local service configuration without reading existing .env."""

import argparse
import secrets
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=Path(".env.local"))
args = parser.parse_args()
if args.output.exists():
    raise SystemExit(f"Preserving existing {args.output}; choose another path")
values = {
    "DRG_DB_PASSWORD": secrets.token_hex(18),
    "DRG_STORAGE_PASSWORD": secrets.token_hex(18),
    "DRG_ARANGO_PASSWORD": secrets.token_hex(18),
}
with args.output.open("x") as stream:
    args.output.chmod(0o600)
    stream.write("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
print(f"Created private {args.output}; values not printed")
