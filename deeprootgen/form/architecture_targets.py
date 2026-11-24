"""Read Architecture Search targets and seeds as typed or pasted on the page."""

import csv
import re
from io import StringIO

TARGET_COLUMNS = {"statistic_name", "statistic_value", "scale"}


def parse_targets(text):
    """Read pasted targets separated by commas, tabs, semicolons or spaces."""
    lines = [line for line in (text or "").replace("\r", "").split("\n") if line.strip()]
    if not lines:
        raise ValueError("Paste targets: a header row statistic_name,statistic_value, then one row per target.")
    header = lines[0]
    delimiter = next((d for d in (",", "\t", ";") if d in header), None)
    if delimiter is None:
        table = [re.split(r"\s+", line.strip()) for line in lines]
    else:
        table = [[cell.strip() for cell in row] for row in csv.reader(StringIO("\n".join(lines)), delimiter=delimiter)]
    names = table[0]
    if set(names) not in (TARGET_COLUMNS, TARGET_COLUMNS - {"scale"}) or len(set(names)) != len(names):
        raise ValueError("The header must be statistic_name,statistic_value with an optional scale column; "
                         f"found {', '.join(names) or 'no columns'}.")
    rows = []
    for number, cells in enumerate(table[1:], start=2):
        if len(cells) < len(names) - ("scale" in names) or len(cells) > len(names):
            raise ValueError(f"Line {number} has {len(cells)} values for {len(names)} columns.")
        row = dict(zip(names, cells))
        rows.append({k: v for k, v in row.items() if k != "scale" or v})
    if not rows:
        raise ValueError("Add at least one target row below the header.")
    return rows


def parse_seeds(text):
    try:
        seeds = [int(value.strip()) for value in re.split(r"[,\s]+", (text or "").strip()) if value.strip()]
    except ValueError as error:
        raise ValueError("Seeds must be whole numbers separated by commas, for example 0, 1.") from error
    if not seeds:
        raise ValueError("Enter at least one seed, for example 0, 1.")
    return seeds
