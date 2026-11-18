#!/usr/bin/env python3
"""Convert a previous generation file to schema 4 in a new file."""
import argparse
import json
from pathlib import Path

from deeprootgen.data_model.migration import convert_input
from deeprootgen.data_model.resolution import load_json_config, resolve_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    converted = convert_input(load_json_config(args.source))
    resolve_config(converted)
    result = json.dumps(converted, indent=2, allow_nan=False)
    with args.destination.open("x", encoding="utf-8") as out:
        out.write(result + "\n")


if __name__ == "__main__":
    main()
