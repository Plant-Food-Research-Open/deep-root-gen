# Options for testing root placement

Use the same focal vine, physical coring geometry and diameter definition
across each comparison. Generate vines before applying any sampling locations.
The following are experimental options for reviewing a spatial RLD model.

| Question | Paired change | What would support the mechanism? |
|---|---|---|
| Does repeating a single vine affect apparent clustering? | Compare translated and independently generated neighbours at the same offsets. | A change in empty-section frequency at matched mean root length, reproduced across independent groups of vines. |
| Can existing secondaries supply more shallow root length? | Give shallow-born secondaries a modest inclination towards horizontal. Keep their attachment sites, compass bearings and lengths matched. | Shallow RLD approaches the observed mean and shallow hits become more frequent without excessive deep loss. |
| Do sibling roots explore the same soil? | Randomly rotate sectors for sibling bearings. Test spacing of attachment sites separately. | Fewer empty sections and less length concentrated in an individual deep hit. |
| Would a different depth distribution of secondary origins help? | Reallocate part of a fixed expected branch count towards shallow primary segments. | The depth profile improves with comparable total length, crown-inclusive dry mass and horizontal spread. |

Start the neighbourhood comparison through the [generator API or offline CLI](../NATIVE_EXECUTION.md#growing-a-neighbourhood-of-vines).
Keep per-plant contributions, counts of completely empty cores, per-depth
occupancy, mean RLD when positive, and ordinary spatial loss. Preserve distinct
test sets for root-growth parameter selection and evaluation. Seed replicates
estimate simulator variability at the measured locations. Testing another
field transect addresses transfer to new locations.

Compare dry tissue density assumptions on fixed geometry when assessing
biomass. Root recovery and species assignment can also affect the measured
response. Replicated recovery samples and a blinded review of shallow and deep
fragments would help quantify those effects.
