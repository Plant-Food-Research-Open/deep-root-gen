"""Offline export of historical reference fixtures."""
from ..cli import _export, _main
from ..run_records import _tracked_run
from .resolution import canonical_input, explain_config, resolve_config
from .simulation import RootSystemSimulation


def simulate(spec, outdir):
    return _export(spec, outdir, resolve_config, canonical_input, RootSystemSimulation)


def main(argv=None):
    return _main(argv, simulate, explain_config)


def tracked_run(config, outdir, *, label, ledger=None, edit=None):
    return _tracked_run(config, outdir, label, ledger, edit, simulate)
