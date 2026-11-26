"""Actual isolated child lifecycle regressions, on the public host matrix."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from blender_agent import glb_isolation as isolation
from blender_agent import glb_worker
from blender_agent.inspect import inspect_asset
from test_glb import triangle_glb


class IsolationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.source=self.root/"triangle.glb"
        self.source.write_bytes(triangle_glb())

    def test_actual_child_and_no_workspace_import(self):
        # A workspace module and startup hook must never shadow trusted code.
        (self.root/"json.py").write_text("raise RuntimeError('workspace import')",encoding="utf-8")
        (self.root/"sitecustomize.py").write_text("raise RuntimeError('startup hook')",encoding="utf-8")
        self.assertEqual(inspect_asset(self.source,self.root)["triangles"],1)

    def test_actual_memory_limit(self):
        package=str(Path(glb_worker.__file__).resolve().parent.parent)
        script=("import sys;sys.path.insert(0,sys.argv[1]);"
                "from blender_agent.glb_worker import _limit_memory;"
                "job=_limit_memory(512*1024*1024)\n"
                "try:\n bytearray(600*1024*1024)\n"
                "except MemoryError:\n print('memory limit enforced')\n"
                "else:\n raise SystemExit(3)")
        result=subprocess.run([sys.executable,"-I","-S","-c",script,package],
                              cwd=self.root,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("memory limit enforced",result.stdout)

    def test_timeout_kills_and_reaps_actual_child(self):
        processes=[]
        original=subprocess.Popen
        def start(*args,**kwargs):
            child=original(*args,**kwargs)
            processes.append(child)
            return child
        with patch.object(isolation,"_command",return_value=[sys.executable,"-I","-S","-c","import time;time.sleep(30)"]), \
             patch.object(isolation,"DEADLINE_SECONDS",0.2), \
             patch.object(isolation.subprocess,"Popen",side_effect=start):
            with self.assertRaisesRegex(RuntimeError,"deadline"):
                isolation.inspect_isolated(self.source,self.root)
        self.assertEqual(len(processes),1)
        self.assertIsNotNone(processes[0].returncode)
        self.assertEqual(inspect_asset(self.source,self.root)["triangles"],1)

    def test_active_cancellation_and_capacity(self):
        processes=[]
        lock=threading.Lock()
        started=threading.Event()
        cancelled=threading.Event()
        original=subprocess.Popen
        def start(*args,**kwargs):
            child=original(*args,**kwargs)
            with lock:
                processes.append(child)
                if len(processes)==2:
                    started.set()
            return child
        with patch.object(isolation,"_command",return_value=[sys.executable,"-I","-S","-c","import time;time.sleep(30)"]), \
             patch.object(isolation.subprocess,"Popen",side_effect=start), \
             concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            tasks=[pool.submit(isolation.inspect_isolated,self.source,self.root,cancelled) for _ in range(2)]
            try:
                self.assertTrue(started.wait(10))
                with self.assertRaisesRegex(RuntimeError,"capacity exhausted"):
                    isolation.inspect_isolated(self.source,self.root)
            finally:
                cancelled.set()
            for task in tasks:
                with self.assertRaisesRegex(RuntimeError,"cancelled"):
                    task.result(timeout=5)
        self.assertEqual(len(processes),2)
        self.assertTrue(all(child.returncode is not None for child in processes))
        self.assertEqual(inspect_asset(self.source,self.root)["triangles"],1)

    def test_pre_cancel_does_not_spawn(self):
        cancelled=threading.Event()
        cancelled.set()
        with patch.object(isolation.subprocess,"Popen") as launch:
            with self.assertRaisesRegex(RuntimeError,"cancelled"):
                isolation.inspect_isolated(self.source,self.root,cancelled)
            launch.assert_not_called()

    def test_malformed_failed_and_oversized_child_responses(self):
        for code,message in (
            ("print('not json')","invalid JSON"),
            ("print('[]')","invalid response"),
            ("print('{\"ok\":true,\"result\":{}}')","incomplete geometry"),
            ("raise SystemExit(7)","worker failed"),
            ("print('x'*300000)","response exceeds"),
        ):
            with self.subTest(code=code),patch.object(isolation,"_command",return_value=[sys.executable,"-I","-S","-c",code]):
                with self.assertRaisesRegex(RuntimeError,message):
                    isolation.inspect_isolated(self.source,self.root)
        self.assertEqual(inspect_asset(self.source,self.root)["triangles"],1)


if __name__=="__main__":
    unittest.main()
