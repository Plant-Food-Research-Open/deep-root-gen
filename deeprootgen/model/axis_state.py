"""Authoritative axis facade over the transitional native workspace.

Birth cylinders are immutable values. Live dimensions/attachment/coordinates
are read through the organ facade, so there is no second mutable geometry.
The final curve and material profile have separate owners.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BirthContext:
    diameter: float
    length: float
    order: int
    root_tissue_density: float


@dataclass
class AxisState:
    organ: object
    biological_id: int
    birth_contexts: tuple
    birth_parent_biological_id: int = 0
    sampled_lengths_cm: tuple = ()
    curve: object = None
    material: object = None

    @property
    def parent(self):
        return self.organ.parent_node

    @property
    def dimensions(self):
        return self.organ.get_lengths()

    @property
    def attachment_arc_cm(self):
        import numpy as np

        parent = getattr(self.parent, "organ", None)
        return 0.0 if parent is None else float(np.cumsum(parent.get_lengths())[parent.segments.index(self.parent)])
