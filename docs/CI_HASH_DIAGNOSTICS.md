# Synthetic hash-failure evidence (local proposal)

The five CI failures at merged fork main `0c9f8ec` represent four distinct
canonical payloads: three physical replay cases and one inactive primary-design
INITIAL, also exercised through the primary-fractions test. The historical
SHA256 assertions remain unchanged. No production code or tolerance changes.

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
repository runtime directories. Publishing this workflow or executing CI is a
separate action; this branch was prepared locally only.

For diagnosis, compare canonical JSON bytes and each nested numeric/type/value
against the four baseline payloads generated on the same merged source. Local
Python3.10.20 and official Python3.10.22, with the same installed dependency
versions, produced identical payload bytes and historical hashes. Disabling
NumPy AVX/FMA features also left hashes unchanged. CI logged matching relevant
package versions, but its actual payloads are not in the current reports. Thus
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
