# Portable public checkpoint references

These text patches reconstruct earlier PUBLIC feature checkpoints inside pytest's
fresh temporary directories. They contain source only, with no observations,
fitted inputs, results, credentials or local-runtime packages.

The baseline is public commit `12b23bfdfaf58e9461af90591bcf5784ddae447d`.
Each patch is the package-only, non-renaming textual diff from that baseline to
the full `reference_commit` in `manifest.json`, generated with:

```text
git diff --no-ext-diff --no-renames --full-index BASE REFERENCE -- deeprootgen
```

References precede the feature whose missing/None/zero behavior is tested:

- parent2 branch zone: `0b8291c5b30b9e026caed6eb41ce0f3dd9f3c7e4`
- order-specific sigma: `25ae482d5126fe10442bdded2210beaf7304d03c`
- primary yaw reversal: `8c8a1460a5da1fcb449f65c5e8b278b5b4c9b5e8`
- tertiary length rank: `d0242ac11835e2ad6246f4160e7387015af8b68a`
- primary attachment distal control: `d36f2ecfd243b944f674539f84dc2d0ea896cd1b`

The manifest binds each patch SHA256 plus the exact preimage/postimage hashes
(or required absence) of every affected module. Tests check those hashes, copy
the current package, apply the patch using local `git apply --check`/`git apply`
outside any checkout/index, then verify the reconstructed modules. No network,
Git object database, external temporary snapshot, canonical checkout or named
dependency overlay is needed at test runtime. Git must be installed; missing or
mismatched fixtures fail instead of skipping assertions.

Only modules that changed are restored. Untouched package files and installed
third-party dependencies are common to both subprocesses. The helper pins the
selected source first in `PYTHONPATH`, preserving arbitrary parent `sys.path`
entries (including symlinks), and each regression asserts the loaded source
module path. The complete existing exact comparisons remain: old versus current,
omitted versus explicit None/zero, nodes/edges/proposals/INITIAL/diagnostics/RNG
where exposed. Float outputs are compared pairwise under the SAME installed
runtime; no platform-specific fixed floating-point digest is an acceptance
fixture. Digests in test receipts identify that run only.

If production source changes, do not loosen hashes, remove assertions or add
skips. Deliberately regenerate and review fixtures from public source identities,
then qualify the portable comparisons again. Production algorithms, tolerances
and historical qualified source epochs are not modified by these test fixtures.
