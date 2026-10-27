# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import local_build


class LocalBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.plugins = ("drasi-source-test", "drasi-reaction-test")
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def record(self):
        directory = self.state / "plugins"
        directory.mkdir()
        artifacts = {}
        for name in ("server", *self.plugins):
            file = (self.state if name == "server" else directory) / name
            file.write_text(name)
            artifacts[name] = {"path": str(file), "sha256": local_build.sha256(file)}
        record = {"runtime": "computationGraph", "artifacts": artifacts}
        self.write_record(record)
        return record

    def write_record(self, record):
        (self.state / "build.json").write_text(json.dumps(record))

    def roots(self, dependency='drasi-lib = { path = "../drasi-core/lib" }', lock=True):
        server = self.root / "drasi-server"
        core = self.root / "drasi-core"
        server.mkdir()
        (core / "lib").mkdir(parents=True)
        (server / "Cargo.toml").write_text("[dependencies]\n" + dependency + "\n")
        (core / "lib/Cargo.toml").write_text("[package]\nname = 'drasi-lib'\n")
        if lock:
            (core / "Cargo.lock").write_text("# fixture\n")
        return server, core

    def test_verified_exact_bundle(self):
        self.record()
        self.assertEqual(local_build.verified_build(self.state, self.plugins),
                         (self.state / "server", self.state / "plugins"))

    def test_missing_record_never_uses_path(self):
        with self.assertRaisesRegex(RuntimeError, "No local build"):
            local_build.verified_build(self.state, self.plugins)

    def test_missing_and_changed_artifacts_are_rejected(self):
        record = self.record()
        artifact = Path(record["artifacts"][self.plugins[0]]["path"])
        artifact.write_text("changed")
        with self.assertRaisesRegex(RuntimeError, "Missing or changed"):
            local_build.verified_build(self.state, self.plugins)
        artifact.unlink()
        with self.assertRaisesRegex(RuntimeError, "Missing or changed"):
            local_build.verified_build(self.state, self.plugins)

    def test_extra_plugin_is_rejected(self):
        self.record()
        (self.state / "plugins/old-library").write_text("old")
        with self.assertRaisesRegex(RuntimeError, "Unexpected files"):
            local_build.verified_build(self.state, self.plugins)

    def test_wrong_package_set_and_runtime_are_rejected(self):
        record = self.record()
        with self.assertRaisesRegex(RuntimeError, "exactly the required"):
            local_build.verified_build(self.state, ("drasi-source-different",))
        record["runtime"] = "different"
        self.write_record(record)
        with self.assertRaisesRegex(RuntimeError, "ComputationGraph"):
            local_build.verified_build(self.state, self.plugins)

    def test_split_plugin_directories_are_rejected(self):
        record = self.record()
        old = Path(record["artifacts"][self.plugins[1]]["path"])
        new = self.state / old.name
        old.rename(new)
        record["artifacts"][self.plugins[1]]["path"] = str(new)
        self.write_record(record)
        with self.assertRaisesRegex(RuntimeError, "one private directory"):
            local_build.verified_build(self.state, self.plugins)

    def test_invalid_packages_fail_before_building(self):
        for plugins in ((), ("drasi-a", "drasi-a"), ("../drasi-a",), ("--all",)):
            with self.subTest(plugins=plugins), patch.object(local_build, "_run") as run:
                with self.assertRaises(ValueError):
                    local_build.build(self.state, plugins)
                run.assert_not_called()

    def test_active_demo_cannot_be_rebuilt(self):
        (self.state / "server.lock").touch()
        with patch.object(local_build, "_run") as run:
            with self.assertRaisesRegex(RuntimeError, "Stop this demo"):
                local_build.build(self.state, self.plugins)
            run.assert_not_called()

    def test_released_runtime_dependency_is_rejected(self):
        server, _ = self.roots('drasi-lib = "0.9"')
        with self.assertRaisesRegex(RuntimeError, "sibling drasi-core"):
            local_build._roots(server)

    def test_wrong_local_runtime_dependency_is_rejected(self):
        server, _ = self.roots('drasi-lib = { path = "../../another/core/lib" }')
        with self.assertRaisesRegex(RuntimeError, "sibling drasi-core"):
            local_build._roots(server)

    def test_missing_lockfile_has_actionable_no_mutation_error(self):
        server, core = self.roots(lock=False)
        with patch.object(local_build, "_run") as run:
            with self.assertRaisesRegex(RuntimeError, "cargo generate-lockfile"):
                local_build.build(self.state, self.plugins, server)
            run.assert_not_called()
        self.assertFalse((core / "Cargo.lock").exists())

    def test_cross_compilation_cannot_reuse_stale_host_outputs(self):
        server, _ = self.roots()
        with patch.dict(os.environ, {"CARGO_BUILD_TARGET": "aarch64-unknown-linux-gnu"}):
            with self.assertRaisesRegex(RuntimeError, "host-local"):
                local_build._roots(server)

    def test_build_copies_each_package_before_later_build_overwrites_target(self):
        server, _ = self.roots()
        target = self.root / "target"
        (target / "debug").mkdir(parents=True)
        calls = []

        def run(argv, *, cwd, capture=False):
            args = list(map(str, argv))
            calls.append(args)
            if args[0] == "cargo":
                self.assertIn("--locked", args)
                for file in (target / "debug").iterdir():
                    file.write_text("overwritten by next package")
                if "--bin" in args:
                    name = "drasi-server"
                else:
                    package = args[args.index("-p") + 1]
                    name = "lib" + package.replace("-", "_") + ".so"
                (target / "debug" / name).write_text(name)
                return None
            if args[0] == "rustc":
                return "rustc test\n"
            return "revision\n" if "rev-parse" in args else ""

        with patch.dict(os.environ, {"CARGO_TARGET_DIR": str(target)}), \
                patch.object(local_build.sys, "platform", "linux"), \
                patch.object(local_build, "_run", side_effect=run):
            local_build.build(self.state, self.plugins, server)
        binary, directory = local_build.verified_build(self.state, self.plugins)
        self.assertEqual(binary.read_text(), "drasi-server")
        for package in self.plugins:
            name = "lib" + package.replace("-", "_") + ".so"
            self.assertEqual((directory / name).read_text(), name)
        builds = [args for args in calls if args[0] == "cargo"]
        self.assertEqual(len(builds), 3)
        self.assertTrue(all(args.count("-p") == 1 for args in builds[1:]))


if __name__ == "__main__":
    unittest.main()
