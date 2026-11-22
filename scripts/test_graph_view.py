# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.

import unittest

import graph_view


def component(identifier, name, role, lifecycle="Running", **observed):
    return {"id": identifier, "name": name, "role": role, "lifecycle": lifecycle,
            "health": observed.get("health", "Unknown"),
            "failurePhase": observed.get("failurePhase"),
            "failureCause": observed.get("failureCause"),
            "waitingReason": observed.get("waitingReason")}


def pipe(source, target, kind="Data"):
    return {"representation": "NativeProvider", "kind": kind,
            "from": {"component": source, "port": "out"}, "to": {"component": target, "port": "in"}}


def subscription(source, target):
    return {"representation": "HostSubscription", "from": source, "to": target}


# Shape of GET /api/v1/instances/<instance>/computation for Source -> Query -> Query -> Reaction.
INSPECTION = {
    "graph": {"id": "__drasi_lib_runtime__", "state": "Running", "revision": 7},
    "components": [
        component("r", "log-reaction", "Reaction"),
        component("s", "my-postgres", "Source"),
        component("q1", "all-messages", "Query"),
        component("q2", "message-counts", "Query"),
        component("i1", "__internal/q1/input/0", "Source"),
        component("o1", "__internal/q1/results", "Sink"),
    ],
    "relationships": [
        subscription("s", "i1"), pipe("i1", "q1"), subscription("s", "q1"),
        pipe("q1", "o1"), pipe("q1", "q2"), pipe("q1", "q2", "Bootstrap"),
        subscription("q2", "r"),
        {"representation": "ControlConnection", "from": "q1", "to": "r"},
    ],
    "resources": [],
}


class GraphViewTests(unittest.TestCase):
    def test_hides_internal_helpers_and_keeps_direct_connections(self):
        visible, edges = graph_view.summarize(INSPECTION)
        self.assertEqual(set(visible), {"s", "q1", "q2", "r"})
        self.assertEqual(edges, {("s", "q1"): {"data"}, ("q1", "q2"): {"data", "bootstrap"},
                                 ("q2", "r"): {"data"}})

    def test_connection_through_a_hidden_helper_is_shown_directly(self):
        inspection = dict(INSPECTION, relationships=[subscription("s", "i1"), pipe("i1", "q1")])
        self.assertEqual(graph_view.summarize(inspection)[1], {("s", "q1"): {"data"}})

    def test_render_orders_by_role_and_explains_failures(self):
        failed = dict(INSPECTION, components=[
            *INSPECTION["components"][:2],
            component("q1", "all-messages", "Query", "Failed", health="Unavailable",
                      failurePhase="Processing", failureCause="lost its dependency"),
            *INSPECTION["components"][3:],
        ])
        text = graph_view.render(failed, "getting-started-server")
        self.assertTrue(text.startswith("Graph getting-started-server (Running)"))
        names = [line.split()[0] for line in text.splitlines() if line.startswith("  ") and
                 not line.startswith("  (") and "->" not in line]
        self.assertEqual(names, ["my-postgres", "all-messages", "message-counts", "log-reaction"])
        self.assertIn("Failed (Unavailable), failed during Processing: lost its dependency", text)
        self.assertIn("(2 internal helper components hidden)", text)
        self.assertIn("  all-messages -> message-counts  (data + bootstrap)", text)
        self.assertIn("  message-counts -> log-reaction\n", text + "\n")
        self.assertNotIn("all-messages -> log-reaction", text)


if __name__ == "__main__":
    unittest.main()
