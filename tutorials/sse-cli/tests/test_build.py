"""Source/installed-artifact provenance checks; no Rust build or services."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build.py"
SPEC = importlib.util.spec_from_file_location("sse_cli_build", SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for path in ("Cargo.toml", "Cargo.lock", "src/main.rs", "scripts/build.py"):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(path)
        self.patcher = patch.object(builder, "ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.destination = self.root / "bin/drasi-sse-cli"
        builder.atomic_write(self.destination, b"owned binary", executable=True)
        self.state = self.root / "state.json"
        self.provenance = {
            "schema": 1, "sourceRoot": str(self.root),
            "sources": builder.source_hashes(), "destination": str(self.destination),
            "sha256": builder.sha256(self.destination),
        }
        self.state.write_text(json.dumps(self.provenance))

    def test_verifies_exact_sources_and_installed_binary(self):
        self.assertEqual(builder.verify(self.destination, self.state), self.provenance)

    def test_rejects_inherited_cross_target_before_invoking_cargo(self):
        with patch.dict(builder.os.environ, {"CARGO_BUILD_TARGET": "some-other-platform"}):
            with patch.object(builder.subprocess, "run") as cargo:
                with self.assertRaisesRegex(ValueError, "Unset CARGO_BUILD_TARGET"):
                    builder.build(None)
                cargo.assert_not_called()

    def test_rejects_changed_and_added_sources(self):
        for path in ("src/main.rs", "src/new.rs", "Cargo.lock", "scripts/build.py"):
            with self.subTest(path=path):
                target = self.root / path
                original = target.read_bytes() if target.exists() else None
                target.write_text("changed")
                with self.assertRaisesRegex(ValueError, "source files changed"):
                    builder.verify(self.destination, self.state)
                if original is None:
                    target.unlink()
                else:
                    target.write_bytes(original)

    def test_rejects_different_binary_checkout_and_destination(self):
        self.destination.write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            builder.verify(self.destination, self.state)
        self.destination.write_bytes(b"owned binary")
        for field in ("sourceRoot", "destination"):
            with self.subTest(field=field):
                changed = dict(self.provenance, **{field: "/elsewhere"})
                self.state.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, "different"):
                    builder.verify(self.destination, self.state)


if __name__ == "__main__":
    unittest.main()
