import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from blender_agent.cli import main
from test_glb import triangle_glb


class CliTests(unittest.TestCase):
    def test_mcp_flags_are_forwarded(self):
        with patch("blender_agent.mcp_server.main", return_value=0) as start:
            self.assertEqual(main(["--workspace", "assets", "--blender", "custom", "--timeout", "7", "mcp"]), 0)
        start.assert_called_once_with(workspace="assets", blender="custom", timeout=7)

    def test_version_and_skills(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(main(["version"]), 0)
        self.assertEqual(json.loads(buffer.getvalue())["version"], "0.0.3")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(main(["skills"]), 0)
        self.assertEqual(len(json.loads(buffer.getvalue())["skills"]), 4)

    def test_read_only_inspection(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "mesh.obj").write_text(
                "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                self.assertEqual(main(["--workspace", directory, "inspect", "mesh.obj"]), 0)
            self.assertEqual(json.loads(buffer.getvalue())["faces"], 1)

    def test_glb_inspection_without_blender(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "triangle.glb").write_bytes(triangle_glb())
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                self.assertEqual(main(["--workspace", directory, "--blender", "missing", "inspect", "triangle.glb"]), 0)
            self.assertEqual(json.loads(buffer.getvalue())["triangles"], 1)

    def test_error_return(self):
        with tempfile.TemporaryDirectory() as directory:
            buffer = io.StringIO()
            with contextlib.redirect_stderr(buffer):
                self.assertEqual(main(["--workspace", directory, "inspect", "../escape.stl"]), 2)
            self.assertFalse(json.loads(buffer.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
