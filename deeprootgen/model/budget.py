"""Fail before allocating native organs, curve stations and output nodes."""

DEFAULT_MAX_BRANCH_PROPOSALS = 100_000


class AllocationBudget:
    def __init__(self, limits):
        self.limits = limits
        self.used = dict(organs=0, stations=0)
        self.minimum_curve_nodes = 1

    def reserve(self, resource, count):
        count = int(count)
        if resource == "stations":
            self.check_nodes(self.minimum_curve_nodes + count - 1)
            self.minimum_curve_nodes += count - 1
        limit = self.limits.get("max_" + resource)
        if limit is not None and self.used.get(resource, 0) + count > limit:
            raise ValueError(f"{resource[:-1].capitalize()} limit exceeded; {resource} are never truncated")
        self.used[resource] = self.used.get(resource, 0) + count

    def check_nodes(self, count):
        limit = self.limits.get("max_nodes")
        if limit is not None and count > limit:
            raise ValueError(f"Node limit exceeded ({count} > {limit})")

    def reserve_branch_proposals(self, count, existing_nodes, intervals, parent_id):
        """Budget the full Poisson draw before allocating its position or cut arrays."""
        limit = self.limits.get("max_branch_proposals", DEFAULT_MAX_BRANCH_PROPOSALS)
        used = self.used.get("branch_proposals", 0)
        if count + used > limit:
            raise ValueError(f"Branch proposal limit exceeded on parent {parent_id}: "
                             f"{count} proposals, {limit - used} remaining; proposals are never truncated")
        self.check_nodes(existing_nodes + intervals + count)
        self.used["branch_proposals"] = used + count
