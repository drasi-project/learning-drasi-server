#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Print the components and connections of a running Drasi Server instance.

Tutorial helpers pass the `data` of
`GET /api/v1/instances/<instance>/computation` to render(). The view keeps
the sources, queries, transformers, sinks and reactions you configured and
hides Server's internal helper components (names starting with `__internal/`).
A connection through hidden helpers is shown as one direct connection.
"""

INTERNAL_PREFIX = "__internal/"
ROLE_ORDER = ("Source", "BootstrapProvider", "Transformer", "Query", "Sink", "Reaction")


def _endpoint(value):
    return value["component"] if isinstance(value, dict) else value


def _internal(component):
    return component["name"].startswith(INTERNAL_PREFIX)


def _depths(visible, edges):
    """Longest distance from a component without visible inputs, so chains read in order."""
    depth = dict.fromkeys(visible, 0)
    for _ in range(len(visible)):
        changed = False
        for source, target in edges:
            if depth[target] < depth[source] + 1:
                depth[target] = depth[source] + 1
                changed = True
        if not changed:
            break
    return depth


def summarize(inspection):
    """Return (visible components, {(from_id, to_id): kinds}) for the graph."""
    components = {component["id"]: component for component in inspection["components"]}
    outgoing = {}
    for relationship in inspection["relationships"]:
        if relationship.get("representation") == "ControlConnection":
            continue
        source, target = _endpoint(relationship["from"]), _endpoint(relationship["to"])
        if source in components and target in components:
            kind = str(relationship.get("kind") or "Data").lower()
            outgoing.setdefault(source, []).append((target, kind))
    visible = {key: value for key, value in components.items() if not _internal(value)}
    edges = {}
    for start in visible:
        pending = [(start, None)]
        seen = set()
        while pending:
            node, kind = pending.pop()
            for target, edge_kind in outgoing.get(node, ()):
                if target in visible:
                    edges.setdefault((start, target), set()).add(kind or edge_kind)
                elif target not in seen:
                    seen.add(target)
                    pending.append((target, kind or edge_kind))
    return visible, edges


def describe_state(component):
    """One short phrase for a component's lifecycle, health and failure."""
    lifecycle = component.get("lifecycle") or component.get("realization") or "Unknown"
    state = lifecycle
    health = component.get("health")
    if health and health not in ("Unknown", "Healthy"):
        state += f" ({health})"
    if component.get("failurePhase"):
        state += f", failed during {component['failurePhase']}"
    if component.get("failureCause"):
        state += f": {component['failureCause']}"
    elif component.get("waitingReason"):
        state += f", waiting: {component['waitingReason']}"
    return state


def render(inspection, instance=None):
    visible, edges = summarize(inspection)
    depth = _depths(visible, edges)

    def order(component):
        role = component["role"]
        rank = ROLE_ORDER.index(role) if role in ROLE_ORDER else len(ROLE_ORDER)
        return rank, depth[component["id"]], component["name"]

    ordered = sorted(visible.values(), key=order)
    width = max((len(component["name"]) for component in ordered), default=0)
    role_width = max([9] + [len(component["role"]) for component in ordered])
    graph = inspection.get("graph", {})
    title = f"Graph {instance}" if instance else "Graph"
    if graph.get("state"):
        title += f" ({graph['state']})"
    lines = [title, "", "Components:"]
    for component in ordered:
        lines.append(
            f"  {component['name'].ljust(width)}  {component['role'].ljust(role_width)}  "
            f"{describe_state(component)}"
        )
    hidden = len(inspection["components"]) - len(visible)
    if hidden:
        lines.append(f"  ({hidden} internal helper components hidden)")
    lines += ["", "Connections:"]
    rank = {component["id"]: position for position, component in enumerate(ordered)}
    for (source, target), kinds in sorted(edges.items(), key=lambda item: (rank[item[0][0]], rank[item[0][1]])):
        names = sorted(kinds, key=lambda kind: (kind != "data", kind))
        label = "" if kinds == {"data"} else f"  ({' + '.join(names)})"
        lines.append(f"  {visible[source]['name']} -> {visible[target]['name']}{label}")
    if not edges:
        lines.append("  (none)")
    return "\n".join(lines)
