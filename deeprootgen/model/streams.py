"""Single owner of simulation randomness.

``native`` is the historical ``default_rng(seed)`` sequence consumed by native
kernels in their original order. Feature laws use keyed streams derived from
(namespace, numerical version, seed, stable biological IDs); never from
exported graph node IDs or Python ``hash()``. Recording, cutting, config
validation and final integrity checks draw nothing. Existing SO4/cohort/
research stream namespaces are unchanged and remain owned by their kernels
until those kernels are migrated into the engine.
"""

import hashlib

import numpy as np
from numpy.random import default_rng


def keyed_generator(namespace, version, seed, *ids):
    """Deterministic, versioned stream independent of draw order elsewhere."""
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError("Keyed feature streams require an explicit nonnegative integer seed")
    parts = [str(namespace), str(version), str(int(seed))]
    for value in ids:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise ValueError("Keyed stream identities must be integer biological IDs")
        parts.append(str(int(value)))
    key = hashlib.sha256(":".join(parts).encode()).digest()
    return default_rng(np.random.SeedSequence(np.frombuffer(key, dtype="<u4")))


COHORT_V5_NAMESPACE = "cohort-root-research-v5"


class RandomStreams:
    """Native sequential stream plus a receipt of every keyed stream issued.

    A keyed stream is created once per key and then continues, so one law's
    draws can span phases (cohort maturity, then origin, from one stream).
    """

    def __init__(self, seed, native=None):
        self.seed = seed
        self.native = default_rng(seed) if native is None else native
        self.issued = []
        self._cache = {}

    def keyed(self, namespace, version, *ids):
        key = ("keyed", namespace, version, *[int(v) for v in ids])
        if key not in self._cache:
            self.issued.append(dict(namespace=namespace, version=version, ids=[int(v) for v in ids]))
            self._cache[key] = keyed_generator(namespace, version, self.seed, *ids)
        return self._cache[key]

    def cohort_v5(self, organ_id, purpose):
        """Historical cohort stream ``SeedSequence([seed, organ, purpose])``."""
        key = ("cohort_v5", int(organ_id), int(purpose))
        if key not in self._cache:
            if isinstance(self.seed, (bool, np.bool_)) or not isinstance(self.seed, (int, np.integer)) or self.seed < 0:
                raise ValueError("Cohort streams require an explicit nonnegative integer seed")
            self.issued.append(dict(namespace=COHORT_V5_NAMESPACE, version="SeedSequence([seed, organ, purpose])",
                                    ids=[int(organ_id), int(purpose)]))
            self._cache[key] = default_rng(np.random.SeedSequence([self.seed, int(organ_id), int(purpose)]))
        return self._cache[key]


def streams_for(simulation):
    """Adopt the simulation's native generator so one owner serves every draw."""
    streams = getattr(simulation, "streams", None)
    if streams is None or streams.native is not simulation.rng:
        streams = RandomStreams(getattr(simulation, "random_seed", None), native=simulation.rng)
        simulation.streams = streams
    return streams
