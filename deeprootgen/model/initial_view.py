"""Detached INITIAL recorder contract; no simulator, RNG or mutator methods.

The two-argument adapter retains attribute reads used by historical recorders.
Tabular reads and metadata reads return detached values. Attempts to assign
snapshot attributes fail; editing a returned DataFrame/dict changes only a copy.
"""

import copy
from types import MappingProxyType


class InitialRecord:
    __slots__ = ("_values",)

    def __init__(self, **values):
        object.__setattr__(self, "_values", MappingProxyType(values))

    def __setattr__(self, name, value):
        raise AttributeError("INITIAL snapshots are read-only")

    def __deepcopy__(self, memo):
        return self

    def __getattr__(self, name):
        try:
            value = self._values[name]
        except KeyError:
            raise AttributeError(name) from None
        # Returning a copy also permits historical copy.deepcopy/dict/list APIs
        # without sharing a mutable object with either execution or the view.
        if isinstance(value, (dict, list)):
            return copy.deepcopy(value)
        if hasattr(value, "copy"):
            return value.copy()
        return value

    def model_dump(self, **kwargs):
        return copy.deepcopy(dict(self._values))


class InitialGraph(InitialRecord):
    def as_df(self):
        return self._values["tables"][0].copy(deep=True), self._values["tables"][1].copy(deep=True)


def initial_view(simulation, parameters):
    """Select recorder data explicitly, excluding live object references."""
    nodes = tuple(InitialRecord(node_data=InitialRecord(**n.node_data.model_dump())) for n in simulation.G.nodes)
    by_id = {n.node_data.node_id: n for n in nodes}
    organs = {}
    for order, group in simulation.organs.items():
        organs[order] = tuple(InitialRecord(
            segments=tuple(by_id[n.node_data.node_id] for n in o.segments),
            **{name: copy.deepcopy(getattr(o, name)) for name in (
                "construction_step_boundary_node_ids", "_construction_step_lengths_cm", "construction_step_provenance",
                "tertiary_length_rank_family", "parent2_zone_diagnostics",
            ) if hasattr(o, name)},
        ) for o in group)
    graph = InitialGraph(nodes=nodes, tables=simulation.G.as_df(),
                         base_node=by_id[simulation.G.base_node.node_data.node_id],
                         bases=tuple(by_id[n.node_data.node_id] for n in simulation.G.bases))
    # The organ mapping itself is detached and its contents are immutable.
    sim_view = InitialRecord(G=graph, organs=organs, random_seed=simulation.random_seed,
                             simulation_tag=simulation.simulation_tag,
                             **{name: copy.deepcopy(getattr(simulation, name)) for name in (
                                 "count_conditioning_diagnostics",
                             ) if hasattr(simulation, name)})
    return sim_view, InitialRecord(**copy.deepcopy(parameters.model_dump()))
