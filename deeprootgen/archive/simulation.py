"""Explicit replay of pre-cutover inputs for historical evidence."""
from ..model.root import RootSystemSimulation as CanonicalSimulation


class RootSystemSimulation(CanonicalSimulation):
    def run(self, input_parameters, *, initial_recorder=None) -> None:
        """Parse, resolve and execute one fresh generation.

        Accepts a validated model (flat, schema 2 or schema 3), a raw JSON
        object, JSON text or a ``pathlib.Path``. Every native input, including
        legacy flat parameters, runs through the same fixed engine lifecycle.
        """
        from .resolution import resolve_config

        resolved = resolve_config(input_parameters)
        if resolved.source_schema == "flat":
            if initial_recorder is not None:
                raise ValueError('INITIAL recording requires extended construction-step execution')
            if getattr(self, '_extended_run_started', False):
                raise ValueError("Use a fresh simulator after an extended run")
        else:
            if len(self.G.nodes) != 1 or self.organs or getattr(self, '_extended_run_started', False):
                raise ValueError("Use a fresh simulator for each extended run")
            if self.random_seed != resolved.seed:
                raise ValueError("Simulator and execution random_seed must match")
            self._extended_run_started = True
            self.result = None
            if initial_recorder is not None:
                # A read-only view of a placed native scaffold: the historical
                # construction-step contract, or schema-3 native construction.
                if resolved.source_schema == "2" and not resolved.laws.writer.get("records"):
                    raise ValueError('INITIAL recording requires construction-step execution')
                if resolved.laws.construction != "native":
                    raise ValueError("INITIAL recording requires native construction with a placed scaffold")
            if resolved.simulator_tag is not None:
                self.simulation_tag = resolved.simulator_tag
        # One engine for every input; ``initial_recorder`` is a read-only view
        # taken at the fixed INITIAL phase after scaffold placement.
        from .engine import execute
        execute(self, resolved, initial_recorder=initial_recorder)
