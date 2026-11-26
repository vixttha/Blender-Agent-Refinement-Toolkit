import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from blender_agent.jobs import (
    MAX_INPUT_BYTES, MAX_LOG_BYTES, MAX_OUTPUT_BYTES, _obj_lock, _publish, _run_blender, execute,
)

TRIANGLE_STL = (
    b"solid triangle\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\n"
    b"vertex 0 1 0\nendloop\nendfacet\nendsolid triangle\n"
)
TRIANGLE_OBJ = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"

INTERRUPT_OBJ_PUBLICATION = """\
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
from blender_agent import jobs

def fixture(command, *, cwd, timeout):
    job = json.loads(Path(command[-1]).read_text())
    output = Path(job["output"])
    output.write_text("mtllib out.mtl\\nv 0 0 0\\nv 1 0 0\\nv 0 1 0\\nf 1 2 3\\n")
    output.with_suffix(".mtl").write_bytes(b"interrupted material")
    Path(job["report"]).write_text('{"mesh_objects": 1, "vertices": 3, "faces": 1, "blender_version": "4.5.16"}')

publish = jobs._publish
def interrupt_after_material(temporary, final, root, *, overwrite):
    publish(temporary, final, root, overwrite=overwrite)
    if final.suffix == ".mtl":
        os._exit(37)

with patch.object(jobs.shutil, "which", return_value="/bin/blender"), \\
     patch.object(jobs, "_run_blender", side_effect=fixture), \\
     patch.object(jobs, "_publish", side_effect=interrupt_after_material):
    jobs.execute("convert", workspace=sys.argv[1], source="input.stl", output="out.obj",
                 overwrite=sys.argv[2] == "overwrite")
"""


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "input.stl").write_bytes(b"untouched")

    @staticmethod
    def fake_success(command, *, cwd, timeout):
        job = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        output = Path(job["output"])
        output.write_bytes({".stl": TRIANGLE_STL, ".obj": TRIANGLE_OBJ}.get(output.suffix, b"mock-export"))
        Path(job["report"]).write_text(
            json.dumps({"mesh_objects": 1, "vertices": 8, "faces": 6,
                        "boundary_edges": 0, "nonmanifold_edges": 0, "blender_version": "4.5.16"}),
            encoding="utf-8",
        )
        return "success"

    @staticmethod
    def fake_obj(command, *, cwd, timeout):
        JobTests.fake_success(command, cwd=cwd, timeout=timeout)
        job = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        output = Path(job["output"])
        library = output.with_suffix(".mtl")
        output.write_bytes(f"mtllib {library.name}\n".encode() + TRIANGLE_OBJ)
        library.write_bytes(b"new material")
        return "success"

    def test_obj_rolls_back_material_when_obj_appears_late(self):
        def late_collision(command, *, cwd, timeout):
            self.fake_obj(command, cwd=cwd, timeout=timeout)
            (self.root / "cube.obj").write_bytes(b"other writer")

        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=late_collision):
            with self.assertRaises(FileExistsError):
                execute("create", workspace=self.root, output="cube.obj", kind="cube")
        self.assertEqual((self.root / "cube.obj").read_bytes(), b"other writer")
        self.assertFalse((self.root / "cube.mtl").exists())

    def test_runtime_report_rejected_before_publication(self):
        for version in (None, "4.5.14", "5.1.99", "4.5.015", "5.2.2", "garbage", 4516):
            with self.subTest(version=version):
                def fake(command, *, cwd, timeout):
                    self.fake_success(command, cwd=cwd, timeout=timeout)
                    job = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
                    report = Path(job["report"])
                    data = json.loads(report.read_text(encoding="utf-8"))
                    if version is None:
                        data.pop("blender_version")
                    else:
                        data["blender_version"] = version
                    report.write_text(json.dumps(data), encoding="utf-8")
                with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
                     patch("blender_agent.jobs._run_blender", side_effect=fake):
                    with self.assertRaisesRegex(RuntimeError, "runtime report is missing or unsupported"):
                        execute("create", workspace=self.root, output="invalid.stl", kind="cube")
                self.assertFalse((self.root / "invalid.stl").exists())

    def test_obj_refuses_missing_material_library(self):
        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=self.fake_success):
            with self.assertRaisesRegex(RuntimeError, "did not produce the OBJ material library"):
                execute("create", workspace=self.root, output="cube.obj", kind="cube")
        self.assertFalse((self.root / "cube.obj").exists())

    def test_cancelled_worker_discards_both_staged_obj_files(self):
        cancelled = threading.Event()

        def cancel_after_export(command, *, cwd, timeout):
            self.fake_obj(command, cwd=cwd, timeout=timeout)
            cancelled.set()

        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=cancel_after_export):
            with self.assertRaisesRegex(RuntimeError, "cancelled before publication"):
                execute("create", workspace=self.root, output="cancelled.obj", kind="cube", cancelled=cancelled)
        self.assertFalse((self.root / "cancelled.obj").exists())
        self.assertFalse((self.root / "cancelled.mtl").exists())
        self.assertFalse(list(self.root.glob("*.pending")))

    def test_obj_overwrite_restores_previous_library_if_obj_replace_fails(self):
        obj = self.root / "out.obj"
        material = obj.with_suffix(".mtl")
        obj.write_bytes(b"old obj")
        material.write_bytes(b"old material")
        from os import replace

        def fail_obj_replace(source, destination):
            if destination == obj:
                raise PermissionError("could not replace OBJ")
            replace(source, destination)

        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=self.fake_obj):
            with patch("blender_agent.jobs.os.replace", side_effect=fail_obj_replace):
                with self.assertRaisesRegex(PermissionError, "could not replace OBJ"):
                    execute("convert", workspace=self.root, source="input.stl", output="out.obj", overwrite=True)
            self.assertEqual(obj.read_bytes(), b"old obj")
            self.assertEqual(material.read_bytes(), b"old material")
            info = execute("convert", workspace=self.root, source="input.stl", output="out.obj", overwrite=True)
        self.assertEqual(info["material_library"], "out.mtl")
        self.assertEqual(material.read_bytes(), b"new material")

    def test_obj_overwrite_preserves_material_referenced_by_source(self):
        source = self.root / "input.obj"
        material = self.root / "out.mtl"
        material.write_bytes(b"source material")
        for reference in ('mtllib "out.mtl"\n', 'mtllib ' + "\\" + '\r\n  "out.mtl"\r\n'):
            with self.subTest(reference=reference):
                source.write_bytes(reference.encode("utf-8-sig"))
                with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
                     patch("blender_agent.jobs._run_blender", side_effect=self.fake_obj):
                    with self.assertRaisesRegex(ValueError, "Source material libraries"):
                        execute("convert", workspace=self.root, source="input.obj", output="out.obj", overwrite=True)
                self.assertEqual(material.read_bytes(), b"source material")
                self.assertFalse((self.root / "out.obj").exists())

    def interrupt_obj_publication(self, overwrite=False):
        result = subprocess.run(
            [sys.executable, "-c", INTERRUPT_OBJ_PUBLICATION, str(self.root),
             "overwrite" if overwrite else "new"],
            capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 37, result.stderr.decode(errors="replace"))
        self.assertEqual((self.root / "out.mtl").read_bytes(), b"interrupted material")
        self.assertEqual(len(list(self.root.glob(".blender-agent-obj-*.pending"))), 1)

    def test_obj_retries_after_process_dies_between_publications(self):
        self.interrupt_obj_publication()
        self.assertFalse((self.root / "out.obj").exists())
        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=self.fake_obj):
            result = execute("create", workspace=self.root, output="out.obj", kind="cube")
        self.assertTrue(result["ok"])
        self.assertEqual((self.root / "out.mtl").read_bytes(), b"new material")
        self.assertFalse(list(self.root.glob(".blender-agent-obj-*.pending")))

    def test_runtime_rejection_preserves_interrupted_obj_journal(self):
        for overwrite in (False, True):
            with self.subTest(overwrite=overwrite), tempfile.TemporaryDirectory() as directory:
                original_root = self.root
                self.root = Path(directory).resolve()
                try:
                    source = self.root / "input.stl"
                    source.write_bytes(TRIANGLE_STL)
                    obj = self.root / "out.obj"
                    material = obj.with_suffix(".mtl")
                    if overwrite:
                        obj.write_bytes(b"previous OBJ")
                        material.write_bytes(b"previous MTL")
                    self.interrupt_obj_publication(overwrite=overwrite)
                    journal, = self.root.glob(".blender-agent-obj-*.pending")
                    snapshot = {p.name: p.read_bytes() for p in journal.iterdir()}
                    obj_before = obj.read_bytes() if obj.exists() else None
                    mtl_before = material.read_bytes()

                    def rejected_report(command, *, cwd, timeout):
                        self.fake_obj(command, cwd=cwd, timeout=timeout)
                        job = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
                        report = Path(job["report"])
                        data = json.loads(report.read_text(encoding="utf-8"))
                        data["blender_version"] = "4.5.14"
                        report.write_text(json.dumps(data), encoding="utf-8")

                    with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
                         patch("blender_agent.jobs._run_blender", side_effect=RuntimeError("Unsupported Blender runtime 4.5.14")):
                        with self.assertRaisesRegex(RuntimeError, "Unsupported Blender runtime"):
                            execute("convert", workspace=self.root, source="input.stl",
                                    output="out.obj", overwrite=overwrite)
                    with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
                         patch("blender_agent.jobs._run_blender", side_effect=rejected_report):
                        with self.assertRaisesRegex(RuntimeError, "runtime report is missing or unsupported"):
                            execute("convert", workspace=self.root, source="input.stl",
                                    output="out.obj", overwrite=overwrite)
                    self.assertEqual({p.name: p.read_bytes() for p in journal.iterdir()}, snapshot)
                    self.assertEqual(obj.read_bytes() if obj.exists() else None, obj_before)
                    self.assertEqual(material.read_bytes(), mtl_before)
                    self.assertEqual(source.read_bytes(), TRIANGLE_STL)
                    with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
                         patch("blender_agent.jobs._run_blender", side_effect=self.fake_obj):
                        result = execute("convert", workspace=self.root, source="input.stl",
                                         output="out.obj", overwrite=overwrite)
                    self.assertTrue(result["ok"])
                    self.assertEqual(obj.read_bytes(), b"mtllib out.mtl\n" + TRIANGLE_OBJ)
                    self.assertEqual(material.read_bytes(), b"new material")
                    self.assertEqual(source.read_bytes(), TRIANGLE_STL)
                    self.assertFalse(journal.exists())
                finally:
                    self.root = original_root

    def test_obj_publication_respects_an_active_process_lock(self):
        lock = self.root / "export.lock"
        script = (
            "import sys\nfrom pathlib import Path\nfrom blender_agent.jobs import _obj_lock\n"
            "with _obj_lock(Path(sys.argv[1])):\n    raise SystemExit(0)\n"
        )
        with _obj_lock(lock):
            result = subprocess.run(
                [sys.executable, "-c", script, str(lock)], capture_output=True, timeout=15,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"another OBJ export is publishing", result.stderr)
            self.assertTrue(lock.is_file())

    def test_interrupted_obj_overwrite_restores_previous_pair_without_overwriting_unrelated_files(self):
        obj = self.root / "out.obj"
        material = self.root / "out.mtl"
        obj.write_bytes(b"previous OBJ")
        material.write_bytes(b"previous MTL")
        self.interrupt_obj_publication(overwrite=True)
        replace = os.replace

        def fail_if_replacing_obj(source, destination):
            if destination == obj:
                raise PermissionError("cannot replace OBJ")
            return replace(source, destination)

        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=self.fake_obj), \
             patch("blender_agent.jobs.os.replace", side_effect=fail_if_replacing_obj):
            with self.assertRaisesRegex(PermissionError, "cannot replace OBJ"):
                execute("convert", workspace=self.root, source="input.stl", output="out.obj", overwrite=True)
        self.assertEqual(obj.read_bytes(), b"previous OBJ")
        self.assertEqual(material.read_bytes(), b"previous MTL")

        self.interrupt_obj_publication(overwrite=True)
        unrelated = self.root / "unrelated.mtl"
        unrelated.write_bytes(b"unrelated material")
        os.replace(unrelated, material)
        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=self.fake_obj):
            with self.assertRaisesRegex(RuntimeError, "Retain the journal"):
                execute("convert", workspace=self.root, source="input.stl", output="out.obj", overwrite=True)
        self.assertEqual(obj.read_bytes(), b"previous OBJ")
        self.assertEqual(material.read_bytes(), b"unrelated material")
        pending, = self.root.glob(".blender-agent-obj-*.pending")
        self.assertEqual((pending / "previous.mtl").read_bytes(), b"previous MTL")

    def test_create_promotes_checked_output(self):
        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=self.fake_success) as runner:
            info = execute("create", workspace=self.root, output="cube.stl", kind="cube")
        self.assertTrue(info["ok"])
        self.assertEqual((self.root / "cube.stl").read_bytes(), TRIANGLE_STL)
        self.assertEqual(info["size_bytes"], len(TRIANGLE_STL))
        self.assertEqual(info["geometry_scope"], "pre_export_scene")
        self.assertEqual(info["blender_version"], "4.5.16")
        self.assertNotIn("blender_version", info["geometry"])
        self.assertEqual(info["artifact_validation"], "structural_mesh")
        self.assertIn("--disable-autoexec", runner.call_args.args[0])

    def test_invalid_exported_stl_is_rejected_despite_valid_scene_report(self):
        def invalid_export(command, *, cwd, timeout):
            self.fake_success(command, cwd=cwd, timeout=timeout)
            job = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
            Path(job["output"]).write_bytes(b"nonempty, but not an STL")

        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=invalid_export):
            with self.assertRaisesRegex(ValueError, "STL"):
                execute("create", workspace=self.root, output="cube.stl", kind="cube")
        self.assertFalse((self.root / "cube.stl").exists())

    def test_convert_never_modifies_input(self):
        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=self.fake_success):
            execute("convert", workspace=self.root, source="input.stl", output="export.glb")
        self.assertEqual((self.root / "input.stl").read_bytes(), b"untouched")

    def test_missing_blender_fails_cleanly(self):
        with patch("blender_agent.jobs.shutil.which", return_value=None):
            with self.assertRaises(FileNotFoundError):
                execute("create", workspace=self.root, output="cube.obj", kind="cube")

    def test_relative_executable_is_anchored_before_working_directory_changes(self):
        blender = str(Path("tools", "blender"))
        with patch("blender_agent.jobs.shutil.which", return_value=blender) as lookup, \
             patch("blender_agent.jobs._run_blender", side_effect=self.fake_success) as runner:
            execute("create", workspace=self.root, blender=blender, output="cube.stl", kind="cube")
        lookup.assert_called_once_with(blender)
        self.assertEqual(runner.call_args.args[0][0], str(Path.cwd() / blender))
        self.assertEqual(runner.call_args.kwargs["cwd"], self.root)

    def test_failure_does_not_publish_output(self):
        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=RuntimeError("worker failed")):
            with self.assertRaises(RuntimeError):
                execute("repair", workspace=self.root, source="input.stl", output="repair.stl")
        self.assertFalse((self.root / "repair.stl").exists())
        self.assertEqual((self.root / "input.stl").read_bytes(), b"untouched")

    def test_existing_output_refused(self):
        (self.root / "cube.stl").write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            execute("create", workspace=self.root, output="cube.stl", kind="cube")

    def test_unsafe_operation_and_size_refused(self):
        with self.assertRaises(ValueError):
            execute("run_python", workspace=self.root, output="cube.stl")
        for value in (float("nan"), float("inf"), -1, 0, 10001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                execute("create", workspace=self.root, output="cube.stl", kind="cube", size=value)

    def test_invalid_timeout_rejected(self):
        for value in (0, 901, True):
            with self.subTest(timeout=value), self.assertRaises(ValueError):
                execute("create", workspace=self.root, output="cube.stl", kind="cube", timeout=value)

    def test_source_cannot_be_replaced_even_with_overwrite(self):
        with self.assertRaises(ValueError):
            execute("repair", workspace=self.root, source="input.stl",
                    output="input.stl", overwrite=True)

    def test_input_size_cap(self):
        (self.root / "huge.stl").write_bytes(b"")
        with (self.root / "huge.stl").open("r+b") as handle:
            handle.truncate(MAX_INPUT_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "size limit"):
            execute("convert", workspace=self.root, source="huge.stl", output="out.stl")

    def test_oversized_output_never_promoted(self):
        temp = self.root / "temp.stl"
        final = self.root / "final.stl"
        with temp.open("wb") as stream:
            stream.truncate(MAX_OUTPUT_BYTES + 1)
        with self.assertRaises(RuntimeError):
            _publish(temp, final, self.root, overwrite=False)
        self.assertFalse(final.exists())

    def test_atomic_no_overwrite_even_when_destination_appears_late(self):
        temp = self.root / "temp.stl"
        final = self.root / "target.stl"
        temp.write_bytes(b"generated")
        final.write_bytes(b"another writer")
        with self.assertRaises(FileExistsError):
            _publish(temp, final, self.root, overwrite=False)
        self.assertEqual(final.read_bytes(), b"another writer")

    def test_parallel_writers_exactly_one_wins(self):
        barrier = threading.Barrier(2)

        def fake_race(command, *, cwd, timeout):
            self.fake_success(command, cwd=cwd, timeout=timeout)
            barrier.wait(timeout=10)
            return "ok"

        def attempt():
            try:
                return execute("create", workspace=self.root, output="shared.stl", kind="cube")
            except FileExistsError:
                return "collision"

        with patch("blender_agent.jobs.shutil.which", return_value="/bin/blender"), \
             patch("blender_agent.jobs._run_blender", side_effect=fake_race):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                a = pool.submit(attempt)
                b = pool.submit(attempt)
                results = [a.result(timeout=15), b.result(timeout=15)]
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(results.count("collision"), 1)
        self.assertEqual((self.root / "shared.stl").read_bytes(), TRIANGLE_STL)

    def test_log_output_cap_terminates_noisy_process(self):
        code = "import sys;sys.stdout.write('x'*" + str(MAX_LOG_BYTES + 100000) + ");sys.stdout.flush()"
        with self.assertRaisesRegex(RuntimeError, "log-size"):
            _run_blender([sys.executable, "-c", code], cwd=self.root, timeout=10)

    def test_subprocess_timeout_is_enforced(self):
        with self.assertRaisesRegex(RuntimeError, "timeout"):
            _run_blender([sys.executable, "-c", "import time;time.sleep(30)"],
                         cwd=self.root, timeout=1)

    def test_blender_does_not_inherit_the_host_input_pipe(self):
        script = (
            "import sys; from pathlib import Path; from blender_agent.jobs import _run_blender;"
            "print(_run_blender([sys.executable, '-c', 'import sys; print(repr(sys.stdin.read()))'],"
            " Path(sys.argv[1]), 2))"
        )
        with subprocess.Popen(
            [sys.executable, "-c", script, str(self.root)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) as process:
            try:
                process.wait(timeout=10)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
            output, error = process.communicate()
        self.assertEqual(process.returncode, 0, error.decode(errors="replace"))
        self.assertEqual(output.strip(), b"''")

    def test_subprocess_nonzero_exit_is_failure(self):
        with self.assertRaisesRegex(RuntimeError, "bad data"):
            _run_blender([sys.executable, "-c",
                          "import sys;print('bad data');sys.exit(4)"],
                         cwd=self.root, timeout=10)


if __name__ == "__main__":
    unittest.main()
