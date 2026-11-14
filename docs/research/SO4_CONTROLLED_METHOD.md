# SO4/T2 controlled static replay method

Public method frozen before local ensemble execution. Research only; no fitting,
parameter adoption, production default changes or measured-scaffold imports.
Published parameter inputs remain in `examples/research/so4_t2_fichtl2024.json`;
this factorization does not claim exact CPlantBox or native legacy replay.

For each matched seed 4101–4110 construct one INITIAL skeleton using DeepRootGen
`init_organs`, `position_secondary_roots`, `position_primary_roots`, in that order.
Do not call `run`, gravity, downward-apex validation or whole-organ rotation.
Source inspection and synthetic invariance checks show that these three
construction/position functions do not read tropism mode or soil surface.
Preserve the supplied finite surface/mode metadata; identical geometry is
qualified across legacy/Fichtl modes and surfaces 0/20 without running treatment.
Save before treatment. This construction is preparation inside the first arm's
attempt, never an extra ensemble run. Preserve all IDs, edges, classifications,
per-segment diameters/lengths, segment subdivision, attachment node and cumulative
parent-arc coordinate. Keep primary scaffold coordinates unchanged in all arms.
Reject a primary scaffold/primary attachment above z=20; no seed replacement.
Higher-order attachment positions move with their parent's replayed geometry,
while their node identity and arc coordinate remain fixed.

| Arm | Insertion heading | Subsequent segment directions |
|---|---|---|
| A | stored legacy first heading transported with parent tangent | stored legacy local turns |
| B | Fichtl-inspired insertion | stored legacy local turns |
| C | stored legacy first heading transported with parent tangent | Fichtl-inspired search |
| D | Fichtl-inspired insertion | Fichtl-inspired search |

Insertion means the first segment is assigned its insertion heading exactly;
search begins at segment 2. A physical boundary correction can override an
infeasible first heading. Record assigned/realised angles and directions. B/C
are diagnostic hybrids; A also omits native legacy gravity/validation.

Legacy directions are a stored sequence, not a native sequential-search model.
A deterministic shortest rotation maps the original parent tangent onto the
current tangent to assign legacy insertion. A shortest rotation from the stored
first heading onto the assigned heading transports its initial frame. Express
each subsequent stored heading in the original preceding segment's transported
frame; map its coordinates into the replay frame. Advance frames with shortest
rotations onto realised directions. This preserves stored turns and torsion and
reconstructs the original polyline with unchanged tangent and no interventions.
For parallel directions use identity; normalized-axis Rodrigues with angle
atan2(cross-norm,dot) avoids near-antiparallel amplification. Below cross-norm
1e-12 an antiparallel
rotation uses the deterministic perpendicular basis from the least-aligned
Cartesian axis. Degenerate direction norms <=1e-12 fail.

Fichtl insertion uses the existing rejection-truncated normal proxy in [0,90]
degrees, uniform azimuth, SO4/T2 means/SDs. Unconstrained search draws the initial
candidate plus stochastically rounded N sqrt(ds) extra candidates. For each,
alpha~Normal(0,sigma sqrt(ds)), beta~Uniform(0,2pi). Order 2 chooses gravity with
probability .65, otherwise plagiotropism; order 3 chooses gravity. Choose minimum
qz or minimum |qz| respectively, with first-index ties. Proposals use the current
rotation-minimizing frame. No boundary filtering influences candidate ranking.

All arms share surface S=20 cm, depth=20-z. After unconstrained selection, for
start p at/below S and length L, retain feasible unit q. If pz+L qz>S, set
c=(S-pz)/L, q'z=c and q'xy=sqrt(1-c²) qxy/||qxy||. This is minimum-angle feasible
heading projection preserving azimuth and full segment length. Floating division
can place an endpoint one ulp above S: deterministically apply nextafter(c,-inf)
until pz+L*c<=S before deriving the horizontal components. Record the nudge count;
this changes heading, never clips the coordinate. For horizontal
norm <=1e-12 draw the boundary azimuth from its keyed stream. Reject nonfinite,
nonunit, nonpositive-length or above-surface starts; never clip coordinates.
Feed realised q' into the next frame/search. This may accumulate surface-following
segments; report corrected edge count, corrected edge length and L*angle radians
as correction arc length. No posthoc rotations or downward-apex constraint.

Random innovations use SHA256-derived NumPy SeedSequence streams keyed by
version, seed, organ ID, zero-based segment index and purpose. Diagnostics
number segments from 1. Boundary draws instead use
node ID. Arm is absent from keys. Insertion/continuation/boundary streams are
separate; unchanged segments share proposal innovations across insertion arms.
Different realised frames can yield different global candidates despite shared
alpha/beta/objective arrays. Per-edge diagnostics include origins, proposed and
accepted headings, candidate innovations and selection, boundary correction and
full scaffold/invariant identities. `proposals.csv` records each one-step
uncorrected endpoint from the actual constrained trajectory's segment origin.
These proposals are not a coherent graph or an independently propagated
no-boundary architecture. There is exactly one physical replay per attempt and
zero counterfactual replays; no extra boundary arm is constructed.

API: `construct_skeleton(parameters, seed)` returns a serializable `Skeleton`;
`replay_arm(skeleton, arm, parameters, 'minimum_angle_projection')` returns node,
edge and one-step proposal tables plus diagnostics. Validate finite geometry,
parent-edge consistency and per-edge length at rel1e-5/abs1e-6; total length must
agree within 1e-8 cm. Frozen node attributes, edges, scaffold and attachment
metadata hashes must match for every arm of a seed. Derive edges and attachment
arc coordinates afresh from each realised node table, compare to INITIAL and
to the persisted invariant manifest of the same seed before declaring complete.
INITIAL nodes/edges are serialized with Python records/JSON for round-trip floats.

The bounded CLI is `scripts/research/so4_controlled_experiment.py --config
configs/research/so4_t2_controlled.json --parameters
examples/research/so4_t2_fichtl2024.json --outdir EXPLICIT_LOCAL_DIRECTORY --execute`.
Without `--execute`, it reports a prepared identity without ensemble work.
`--prepare` additionally creates a durable manifest and content-addressed byte
snapshots without any attempt; generation timing starts only with `--execute`.
Repeat `--reference PATH` for every external input/baseline reference to freeze
its exact bytes alongside source/config/tests and interpreter/package versions.
One controller and one child worker; two CPU threads, 60 seconds per attempt,
900 seconds generation, 40 new attempts including failures, no automatic retry,
1 GiB new outputs. Atomic exclusive durable reservation precedes construction or replay. Publish
fsynced complete bytes by linking a unique temporary file for exclusive creation,
or replacing for updates; stale temporary names cannot block publication.
Interrupted reserved/running attempts become abandoned once no live worker holds
the attempt lock. Failed/abandoned pairs remain consumed and are skipped, while
unattempted pairs can proceed without retries. Corrupt reservation slots retain
the cap and stop for explicit recovery; never regenerate their identities.
Saved INITIAL reuse and resume require identical source/config/interpreter
manifest. Failed construction or truncated INITIAL stops before reserving the
other arms; no reconstruction, replacement seed or arm cascade. Persist a receipt
from the entire ledger in the controller's finally block, including old failures
and unreadable consumed slots. Budgets and the declared parameter path, bytes and
settings are enforced against the CLI. Generation deadline includes downtime;
reserve no new attempt with less than its full 60-second allowance remaining.
The outer caller owns the 1800-second end-to-end budget including data analysis;
runner receipts expose generation timing.

Synthetic tests use public fixtures and write separate logs/JUnit. One larger
seed-314159 INITIAL has at least 1000 segments and is replayed across all four
arms to check numerical surface handling and invariants. It is separate from
seeds 4101–4110 and the ensemble ledger. Long oblique crossings and continuation/
daughter origins exercise projection ulp nudges. Crash/resume tests use synthetic
ledgers. These are algorithm checks, not biological validation or ensemble attempts.
