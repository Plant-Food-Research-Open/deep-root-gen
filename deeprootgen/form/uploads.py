"""Validate CSV uploads before replacing dashboard datasets."""

import base64
import csv
from io import StringIO

import pandas as pd
from dash import no_update


def load_csv_upload(
    contents: list | None,
    filenames: list | None,
    required_columns: tuple[str, ...] = (),
) -> tuple:
    """Return parsed and raw stores plus feedback, retaining the stores on error."""
    if not contents or not contents[0]:
        return no_update, no_update, no_update

    filename = (filenames or ["CSV file"])[0] or "CSV file"
    try:
        metadata, _, encoded = contents[0].partition(",")
        if not metadata.startswith("data:") or not metadata.endswith(";base64"):
            raise ValueError("Select a CSV file.")
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8-sig")
        reader = csv.reader(StringIO(decoded), strict=True)
        header = next((row for row in reader if row), [])
        if not header or any(not name.strip() for name in header):
            raise ValueError("The CSV needs a header with named columns.")
        if len(set(header)) != len(header):
            raise ValueError("The CSV has duplicate column names.")
        missing = set(required_columns) - set(header)
        if missing:
            raise ValueError("Missing columns " + ", ".join(sorted(missing)) + ".")
        if any(row and len(row) != len(header) for row in reader):
            raise ValueError(
                "Every CSV row must have the same number of fields as the header."
            )
        df = pd.read_csv(StringIO(decoded))
        if df.empty:
            raise ValueError("The CSV has no data rows.")
    except (ValueError, csv.Error) as exc:
        return no_update, no_update, f"Could not load {filename}. {exc}"

    return (
        {"label": filename, "values": df.to_dict("records")},
        {"values": encoded},
        f"Loading data from {filename}",
    )
