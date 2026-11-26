"""Benign version fixtures; do not execute vulnerable Blender binaries."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from blender_agent import blender_worker as worker


class RuntimePolicyTests(unittest.TestCase):
    def test_patched_release_branches(self):
        for version in ((4, 5, 15), (4, 5, 16), (4, 5, 99), (5, 2, 3), (5, 2, 4)):
            with self.subTest(version=version):
                self.assertEqual(worker.require_runtime(version, "release"), ".".join(map(str, version)))

    def test_affected_unknown_and_nonrelease_versions(self):
        rejected = [
            ((4, 1, 0), "release"), ((4, 5, 0), "release"), ((4, 5, 14), "release"),
            ((5, 0, 99), "release"), ((5, 1, 99), "release"), ((5, 2, 2), "release"),
            ((5, 3, 0), "release"), ((6, 0, 0), "release"),
            ((4, 5, 16), "alpha"), ((5, 2, 4), "beta"), ((5, 2, 4), "rc"),
            ((4, 5, 16), None), ((4, 5), "release"), ((4, 5, -1), "release"),
            ((4, 5, True), "release"), (("4", 5, 16), "release"),
        ]
        for version, cycle in rejected:
            with self.subTest(version=version, cycle=cycle):
                with self.assertRaisesRegex(RuntimeError, "stable Blender 4.5 LTS"):
                    worker.require_runtime(version, cycle)

    def test_rejection_precedes_manifest_read_and_blender_operations(self):
        fake_bpy = SimpleNamespace(app=SimpleNamespace(version=(4, 5, 14), version_cycle="release"))
        with patch.dict(sys.modules, {"bpy": fake_bpy}), \
             patch.object(worker, "_clear") as clear, \
             patch.object(worker, "_import") as load, \
             patch.object(worker, "_export") as export, \
             patch.object(worker.Path, "read_text") as read:
            with self.assertRaisesRegex(RuntimeError, "Unsupported Blender runtime 4.5.14"):
                worker.main()
            for call in (clear, load, export, read):
                call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
