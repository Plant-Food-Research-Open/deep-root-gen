# Partial excavation observations

The static schema-4 engine can construct mature structural architectures using
per-parent-order branching laws. Use root order for anatomical parentage.
Root function, chronological age, the local branching-diameter gate, and the
diameter classes used to summarize sampled material each describe different
properties.

## Measurement support

| Measurement | Observation to retain | Use |
| --- | --- | --- |
| Complete crown census | Count of first-order axes for the recorded vine | Fix the initial count when completeness is documented. |
| Diameter or taper | Local diameter in cm at a named station, or taper rate per cm on its measured segment | Keep the observed location, diameter range and segment support. |
| Recovered whole-axis contour | Complete axis length, or a lower bound when the tip is broken or cut by the excavation | Use only on the recorded anatomical axis and coordinate frame. |
| Segment to a branch or break | Segment length on the observed path, in cm | Classify the segment by its recorded endpoints. Interbranch distance needs consecutive branch endpoints. |
| Daughter count | Observed count on defined parent orders and support, or a lower bound when incomplete | Preserve observed zeros separately from missing data. |
| Paired soil-core observations | RLD and dry mass at the measured locations, depth intervals and diameter support | Keep whole cores together when selecting and evaluating candidates. |

The [excavation observation helper](../../deeprootgen/research/excavation.py)
stores exact measurements, lower bounds and missing values. Its length
operator clips a whole centreline to a known XYZ box. Provide the placement
of that box in the simulated coordinate frame and an explicit completeness
flag. Entering and leaving the box can yield several recovered intervals of
the same root. A root entirely outside the support returns a missing
whole-axis measurement.

The [archive crosswalk](../../scripts/data/mature_vine_archive.py) derives raw
axes from serial point IDs and explicit attachment links, and checks RSML
nesting separately. After checking centimetre units and the stem landmarks,
it matches full point sequences under the declared frame and verifies
parentage. It reports raw-only and unmatched RSML axes. Duplicate raw IDs
raise an error by default. First/last sensitivity modes retain both occurrences
for the source comparison and exclude the affected vine from geometric
summaries.

## Recovery sensitivity

An assumed recovery fraction applies to a declared parent order and sampled
structural-root support. For an illustrative fraction of 1/h, one comparison
can propose hN daughters when the reference conditional draw is N. This
retains the reference per-parent probability, daughter positions law, the
diameter gate, and the supplied crown inputs. Accepted counts can respond
nonlinearly as diameter eligibility and descendants enter the calculation.
Keep the measurement support and independent soil-core targets fixed.

The design should record which root types, diameters and parts of an axis the
sampling method could detect. The ratio of counts in two export formats
measures representation differences. A single incomplete inventory cannot
identify the recovery fraction or full-system branching distribution.

Use the [canonical execution guide](../NATIVE_EXECUTION.md) for the branching
controls and run receipts. Keep empirical configurations and comparison
outputs with the local research record.
