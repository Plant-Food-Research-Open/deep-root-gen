"""Read-only integrity checks for all extended native execution contracts."""

import numpy as np


def validate_result(simulation):
    nodes = {node.node_data.node_id: node for node in simulation.G.nodes}
    if len(nodes) != len(simulation.G.nodes):
        raise ValueError("Duplicate graph node identity")
    expected, bases = set(), []
    children = {nid: [] for nid in nodes}
    for nid, node in nodes.items():
        row = node.node_data
        if not np.isfinite(
            [row.x, row.y, row.z, row.length, row.diameter, row.root_tissue_density]
        ).all():
            raise ValueError("Non-finite graph geometry or material")
        if min(row.length, row.diameter, row.root_tissue_density) < 0:
            raise ValueError("Negative root material")
        if row.order == 0:
            if row.parent_id != -1 or row.length != 0:
                raise ValueError("Root base carries an incoming material edge")
            bases.append(nid)
            continue
        if row.parent_id not in nodes:
            raise ValueError("Missing graph parent")
        if row.plant_id != nodes[row.parent_id].node_data.plant_id:
            raise ValueError("Cross-vine material edge")
        children[row.parent_id].append(nid)
        expected.add((row.parent_id, nid))
    pairs = [(e.edge_data.parent_id, e.edge_data.child_id) for e in simulation.G.edges]
    if len(pairs) != len(expected) or set(pairs) != expected:
        raise ValueError("Graph edges disagree with node parents")
    traversal = list(bases)
    for nid in traversal:
        traversal.extend(children[nid])
    if len(traversal) != len(nodes) or len(set(traversal)) != len(nodes):
        raise ValueError("Graph is not a rooted forest")
    registered = []
    for order, organs in simulation.organs.items():
        for organ in organs:
            ids = [n.node_data.node_id for n in organ.segments]
            if not ids or any(nodes[n].node_data.order != order for n in ids):
                raise ValueError("Native organ membership is inconsistent")
            if [nodes[n].node_data.parent_id for n in ids] != [
                organ.parent_node.node_data.node_id,
                *ids[:-1],
            ]:
                raise ValueError("Native organ chain is stale")
            if any(nodes[n].organ is not organ for n in ids):
                raise ValueError("Native node owner is stale")
            registered.extend(ids)
    material = {nid for nid in nodes if nodes[nid].node_data.order > 0}
    if len(registered) != len(material) or set(registered) != material:
        raise ValueError("Native organs do not cover the material graph")
