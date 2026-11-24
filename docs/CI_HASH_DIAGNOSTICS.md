# Synthetic hash-failure evidence (local proposal)

The five CI failures at merged fork main `0c9f8ec` represent four distinct
canonical payloads: three physical replay cases and one inactive primary-design
INITIAL, also exercised through the primary-fractions test. The historical
SHA256 values are retained as historical provenance. The repair compares exact
canonical historical/current bytes under the same installed runtime. No
production code or numerical tolerances change.

The two test entrypoints catch only their final AssertionError, write the
invented payload(s) with the exact production JSON serialization, and re-raise.
Passing checks emit nothing. Collection requires DRG_SYNTHETIC_FAILURE_DIR.
Metadata includes expected/actual hashes, byte counts, Python/libc/platform,
selected package versions and NumPy CPU feature flags, not arbitrary environment
variables, credentials, hostname, git remotes or user filesystem data. Separate
unique case directories preserve repeated failures without overwriting them.
Only these checked-in synthetic cases call the collector. Do not use it with
observations or general application payloads.

The proposed workflow points collection at a fresh runner temporary directory
and retains that directory only on failure for seven days. It does not upload
repository runtime directories. The owner-authorized diagnostic run captured the synthetic evidence described
below. This document does not authorize additional publication or runs.

For diagnosis, compare canonical JSON bytes and each nested numeric/type/value
against the four baseline payloads generated on the same merged source. Local
Python3.10.20 and official Python3.10.22, with the same installed dependency
versions, produced identical payload bytes and historical hashes. Disabling
NumPy AVX/FMA features also left hashes unchanged. CI logged matching relevant
package versions; the initial reports lacked payloads, subsequently captured by
the diagnostic workflow. Thus
Python patch version alone is not an established cause. Keep the exact hashes;
do not treat capture of a different hash as approval to replace the reference.

## Separate documentation deployment failure

The Documentation run built HTML, then GitHub rejected the deploy action's
force-push to gh-pages with `Permission ... denied to github-actions[bot]` (403).
The current YAML already declares contents:write. Adding that permission again
is not a demonstrated fix. Check effective token permissions, repository/org
Actions restrictions, gh-pages rules and intended publishing repository first.
Do not widen permissions, replace credentials or force-push as a diagnostic.

If the fork should not publish documentation, retain the build but gate the
Deploy step to the authoritative upstream repository. That changes publication
behavior and needs the owner's decision. If fork publication is intended,
consider an approved Pages artifact/deploy-pages workflow with narrowly scoped
pages:write/id-token:write and its protected environment, rather than a branch
force-push. This also requires repository Pages configuration/permission review.
No deployment workflow or repository settings have been changed here.

## Evidence and repaired acceptance contract

The diagnostic CI run 43808715210 captured all five failing cases. Four distinct
payloads differ only in floating-point values: 4, 31 and 179 fields in the replay
cases, with maximum absolute differences 2.78e-17, 1.78e-15 and 3.20e-14. The
INITIAL differs in 88 fields, maximum 2.11e-15. No dictionary keys, list lengths,
scalar types, categorical values or topology changed. The differences include
headings and propagated coordinates, not just formatting. The failing runner
reported Python3.10.22/glibc2.43 and matching relevant package versions. The
precise numerical-library origin is not established by these observations.

Two added source-only reference fixtures authenticate the exact pre-OU physical
module (SHA256 e4e7e4b545476e5e9944b1e094809b51780cfb232b8bfe2d78a7521f7434a16a)
and the three pre-primary-design modules against source hashes recorded before
those changes. These snapshots are independent pre-feature code, not expected
outputs regenerated from the current implementation. The portable-reference
mechanism checks patch/preimage/postimage hashes, loads historical package files
in a subprocess, and uses the same installed dependencies as the current side.
Unchanged dependencies/helpers are shared, consistent with the earlier portable
feature regression tests; this is feature-epoch regression, not certification of
every transitive runtime dependency. No test depends on a developer snapshot path.

The three original invented physical cases and inactive primary-design case
remain. Their entire canonical payloads must match exactly, including diagnostics
and serialized floats. The omitted/explicit-none identity equality also remains.
The old fixed digest strings stay as provenance; no new CI digest is accepted.
Failure evidence now includes the historical payload for direct comparison.
Negative controls prove a changed payload fails, corrupted reference patch or
postimage fails authentication, and diagnostics do not swallow the assertion.

## Fork documentation deployment policy

The fork has no configured Pages site (`has_pages: false`, verified 16 November
2026); the README points to the authoritative PFR documentation site. The
documentation workflow still builds on fork main pushes and manual dispatches,
but its deployment step now runs only in
`Plant-Food-Research-Open/deep-root-gen`. Upstream triggers and deployment action
are unchanged. This deliberately skips fork publication; it does not repair or
claim to repair the previous bot push HTTP 403. No token permissions, repository
settings, credentials, or Pages configuration were changed.
