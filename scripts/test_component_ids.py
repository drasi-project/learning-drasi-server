# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.

import unittest

from component_ids import component_ids


FIRST = "b20c42ee-59a1-441f-a549-87a72be1f1e9"
SECOND = "e4ba7cee-4b9b-4b24-ad4e-a58f0e04d481"


class ComponentIdTests(unittest.TestCase):
    def test_names_and_uuids_are_separate(self):
        self.assertEqual(
            component_ids([{"name": FIRST, "id": SECOND}], {FIRST}, "queries"),
            {FIRST: SECOND},
        )

    def test_duplicate_names_or_ids_are_errors(self):
        for second in ({"name": "orders", "id": SECOND}, {"name": "other", "id": FIRST}):
            with self.assertRaisesRegex(RuntimeError, "Duplicate"):
                component_ids([{"name": "orders", "id": FIRST}, second])

    def test_missing_extra_and_malformed_records_are_errors(self):
        for records in (
            None, {}, [None], [{"id": FIRST}], [{"name": "orders", "id": "orders"}],
            [{"name": "orders", "id": FIRST.upper()}], [],
            [{"name": "other", "id": FIRST}],
        ):
            with self.subTest(records=records), self.assertRaises(RuntimeError):
                component_ids(records, {"orders"}, "queries")


if __name__ == "__main__":
    unittest.main()
