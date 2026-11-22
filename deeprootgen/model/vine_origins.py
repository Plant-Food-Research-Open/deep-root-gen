"""Resolve and select coherent model-frame vine origins."""

from math import fsum


VINE_ORIGIN_STREAM = "feature.vine_origin_catalogue"
VINE_ORIGIN_VERSION = "1"


def _origin_geometry(entry, primary_count):
    if entry.layout == "common_point":
        return dict(layout=entry.layout, entry_id=entry.entry_id, origin=entry.origin.model_dump())
    primaries = sorted(entry.primaries, key=lambda origin: origin.index)
    if len(primaries) != primary_count or any(origin.index != index for index, origin in enumerate(primaries)):
        raise ValueError(
            f"Vine-origin entry {entry.entry_id!r} requires exactly primary indices 0..{primary_count - 1} "
            "for parameters.primary_root_count"
        )
    return dict(layout=entry.layout, entry_id=entry.entry_id,
                primaries=[origin.model_dump(exclude_none=True) for origin in primaries])


def resolve_vine_origins(settings, primary_count, surface_z_cm):
    """Compile the active selection pool without presentation or source metadata."""
    selection = settings.selection.model_dump()
    entries = sorted(settings.entries, key=lambda entry: entry.entry_id)
    if selection["mode"] == "fixed":
        entries = [entry for entry in entries if entry.entry_id == selection["entry_id"]]
    geometry = [_origin_geometry(entry, primary_count) for entry in entries]
    heading_owners = {"primaries" in entry and "heading_unit" in entry["primaries"][0] for entry in geometry}
    if len(heading_owners) != 1:
        raise ValueError("Selectable vine-origin entries must agree on primary heading ownership")
    law = dict(layout=settings.layout, catalogue_version=settings.catalogue_version,
               coordinate_frame=settings.coordinate_frame, selection=selection, entries=geometry,
               measured_headings=heading_owners.pop(), surface_z_cm=surface_z_cm)
    if selection["mode"] == "sample":
        largest = max(entry.weight for entry in entries)
        relative = [entry.weight / largest for entry in entries]
        total = fsum(relative)
        weights = [weight / total for weight in relative]
        if any(weight <= 0 for weight in weights):
            raise ValueError("Vine-origin weights cannot be normalized to finite positive probabilities")
        law.update(weights=weights, stream_namespace=VINE_ORIGIN_STREAM, stream_version=VINE_ORIGIN_VERSION)
    return law


def select_vine_origin(law, streams):
    """Select one entry with a run-level key, or select the fixed entry without a draw."""
    if law["selection"]["mode"] == "fixed":
        return law["entries"][0], 1.
    rng = streams.keyed(law["stream_namespace"], law["stream_version"])
    index = int(rng.choice(len(law["entries"]), p=law["weights"]))
    return law["entries"][index], law["weights"][index]
