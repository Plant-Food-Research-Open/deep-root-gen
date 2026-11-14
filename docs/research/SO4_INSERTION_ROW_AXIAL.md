# Optional axial row preference for insertion azimuth

## Hypothesis and scope

Primary orientation alone does not prescribe daughter orientation when circumferential insertion azimuth is uniform. A conditional row preference in that azimuth may represent along-row structure without changing sampled parent-relative polar angles, current lengths, attachments, counts or primary scaffold. This is a separately evaluated research anisotropy assumption. It is NOT a row-tropism coefficient or additional biological equation attributed to Fichtl2024. Its physical cause is unresolved (scaffold history, environment, sampling or other mechanisms). The published polar/tropism evidence is retained separately.

## Rule fixed before implementation

Add research_insertion_row_axial_kappa: optional mapping of selected orders2/3 to finite nonnegative dimensionless concentration. Default None and explicit kappa0 retain the original heading exactly. Reject empty/unsupported orders. Require explicit matching constructor/input seeds and Fichtl mode when active. Controlled application is to Fichtl insertion (armsB/D); fail clearly if active controls are requested for legacy insertion (armsA/C). No continuation-law change is bundled.

For unit parent tangent t and fixed physical along-row axis r=(0,1,0), call the existing insertion sampler exactly once unchanged to obtain h0, retaining its full shared polar/azimuth RNG schedule. Let c=h0 dot t, s=norm(h0-c*t), v=r-(r dot t)*t, rho=norm(v). If kappa0, rho<1e-12 or s<1e-12, retain h0 exactly and record the applicable fallback. Otherwise e=v/rho, b=t cross e; draw eta~vonMises(0,kappa) and an independent fair binaryB using a separate versioned SHA256-derived stream keyed by authoritative seed, order, biological organID and purpose. Put phi=eta/2+B*pi (mod2*pi), and h=c*t+s*(cos(phi)*e+sin(phi)*b), normalizing only rounding error. This has transverse axial density proportional to exp(kappa*cos(2phi)). It preserves the sampled parent-relative polar angle. Axial symmetry refers to the transverse component, not necessarily globally opposite daughter headings.

The parent-parallel-row fallback is physical degeneracy: no circumferential choice can alter row projection while preserving the polar angle. Global inclination/depth may change under the nondegenerate rule. Subsequent Fichtl-inspired continuation can dissipate this initial preference and remains unchanged. Surface projection may override any insertion; record original, biased and realised post-boundary headings.

## Diagnostics and numerical checks

Record old/new headings, old/new polar angles, row projection norm, sampled phi/branch, stream identity, fallback and realised post-boundary heading. Verify unchanged default/kappa0 geometry and shared RNG state; unit headings and polar-angle equality at existing tolerances; deterministic independent keyed streams; axial symmetry; parallel/near-parallel/zero-polar handling; finite graphs, identical IDs/topology/counts/lengths/attachments and primary scaffold across matched seeds. Add an invented combined origin+CDF+redistribution+yaw+ArmD integration fixture and measure initial-versus-later row projection, distinguishing boundary interventions. No existing numerical tolerance is relaxed.

## Separate local experiment

Freeze source, qualify public synthetic tests and independently review public code before local runs. Hold the prior empirical current-length/origin/scaffold and primary-yaw configuration fixed. Evaluate concentration1,2,4 on ten fixed selection seeds4101..4110 in that order, stopping if all13trait/3profile criteria pass. These search values are engineering assumptions, not measured paper inputs. At most30attempts for this declared grid, with failures and reruns counted. Use a separately frozen fresh-seed block after selecting a configuration. All actual observations, fitted arrays and comparison artifacts remain local. Fresh seeds address MonteCarlo stability only; no biological or unseen-vine validation.

## Post-qualification interpretation notes

The reference axis is model-frame+y, assumed along-row under the declared observation mapping; primary yaw does not rotate that axis. An operator-level synthetic graph check is required before local trials. For a row-aligned dipping parent t=(0,cos(a),-sin(a)), the preferred transverse axis is e=(0,sin(a),cos(a)): concentration can change vertical structure strongly as well as row structure. Report both effects and surface overrides. The frozen v1 rule is unchanged.

Matching stream keys do not monotonically couple NumPy vonMises draws across concentration values. Describe the grid as common-scaffold/common-branch pairing with common continuation innovations, conditional on fixed organ identities. Pin NumPy for selection, fresh-seed qualification and reproduction. INITIAL hashes may differ because parameters are embedded; compare nodes/edges/organs and verify actual replay settings agree with the declared non-null controls.
