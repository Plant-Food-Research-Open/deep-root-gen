# Public SO4/T2 research input

`so4_t2_fichtl2024.json` is the explicit paper-informed static input for the
optional research mode. It is not a physiological calibration. See the
[research-mode guide](../../docs/research/FICHTL_RESEARCH_MODE.md) for units,
length scaling, angle truncation, offset-frame limitations and offline commands.
Published input bytes are preserved; this draft introduces no release adoption.


## Invented search and five-order examples

Start with `search_synthetic.json` and [the search contract](../../docs/research/NOTEBOOK_PARAMETER_SEARCH.md). Validate without `--execute` before running. The reference and parameters are invented plumbing examples, not a calibration.

`five_order_primary_mass_synthetic.py` demonstrates separate optional construction and supplied-graph material interfaces. See [the five-order contract](../../docs/research/FIVE_ORDER_PRIMARY_AND_MASS_METHOD.md). Do not equate root order with diameter-defined fine-root mass.
