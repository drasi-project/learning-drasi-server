#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Validate named component inventories and bind API operations to actual UUIDs."""

from uuid import UUID


def component_ids(components, expected=None, kind="components"):
    if not isinstance(components, list):
        raise RuntimeError(f"Invalid {kind} inventory: expected a list")
    bindings = {}
    seen = set()
    for component in components:
        if not isinstance(component, dict):
            raise RuntimeError(f"Invalid {kind} component record")
        name, identifier = component.get("name"), component.get("id")
        if not isinstance(name, str) or not name:
            raise RuntimeError(f"Invalid {kind} component name")
        if not isinstance(identifier, str):
            raise RuntimeError(f"Missing UUID for {kind} component '{name}'")
        try:
            canonical = str(UUID(identifier))
        except ValueError as error:
            raise RuntimeError(f"Invalid UUID for {kind} component '{name}'") from error
        if canonical != identifier:
            raise RuntimeError(f"Noncanonical UUID for {kind} component '{name}'")
        if name in bindings or identifier in seen:
            raise RuntimeError(f"Duplicate name or UUID in {kind} inventory")
        bindings[name] = identifier
        seen.add(identifier)
    if expected is not None and set(bindings) != set(expected):
        raise RuntimeError(f"Unexpected {kind}: expected names {sorted(expected)}, got {sorted(bindings)}")
    return bindings
