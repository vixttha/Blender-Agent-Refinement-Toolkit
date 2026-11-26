"""Bounded, killable GLB child process; no asset-provided executable code."""
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import threading
import time

MEMORY_BYTES = 512 * 1024 * 1024
DEADLINE_SECONDS = 60
MAX_RESPONSE_BYTES = 256 * 1024
_SLOTS = threading.BoundedSemaphore(2)


def _command(source, root):
    return [sys.executable, "-I", "-S", str(Path(__file__).with_name("glb_worker.py")),
            str(source), str(root)]


def _active(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise RuntimeError("GLB inspection cancelled before publication.")


def inspect_isolated(source, root, cancelled=None):
    _active(cancelled)
    if not _SLOTS.acquire(blocking=False):
        raise RuntimeError("GLB inspection capacity exhausted; retry after another inspection finishes.")
    try:
        _active(cancelled)
        deadline = time.monotonic() + DEADLINE_SECONDS
        # The fixed child emits at most one bounded JSON response. Its stderr
        # is discarded; asset data is never interpreted as commands or pickle.
        with subprocess.Popen(_command(source, root), cwd=root,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0) as child:
            try:
                while True:
                    _active(cancelled)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError("GLB inspection exceeded its deadline.")
                    try:
                        output, _ = child.communicate(timeout=min(0.05, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        continue
                _active(cancelled)
                if time.monotonic() >= deadline:
                    raise RuntimeError("GLB inspection exceeded its deadline.")
                if child.returncode != 0:
                    raise RuntimeError("GLB inspection worker failed or exceeded its resource limit.")
                if len(output) > MAX_RESPONSE_BYTES:
                    raise RuntimeError("GLB inspection worker response exceeds its limit.")
                try:
                    envelope = json.loads(output)
                except (UnicodeError, ValueError) as exc:
                    raise RuntimeError("GLB inspection worker returned invalid JSON.") from exc
                if not isinstance(envelope, dict):
                    raise RuntimeError("GLB inspection worker returned invalid response.")
                if envelope.get("ok") is True and isinstance(envelope.get("result"), dict):
                    result = envelope["result"]
                    if (result.get("format") != "glb"
                            or result.get("inspection") != "embedded_base_geometry"
                            or not isinstance(result.get("sha256"), str)
                            or not re.fullmatch(r"[0-9a-f]{64}", result["sha256"])
                            or type(result.get("size_bytes")) is not int
                            or type(result.get("usable_triangles")) is not int
                            or result["usable_triangles"] < 1
                            or result.get("name") != source.name):
                        raise RuntimeError("GLB inspection worker returned incomplete geometry metadata.")
                    return result
                if envelope.get("ok") is False and isinstance(envelope.get("error"), str):
                    if envelope.get("kind") == "invalid":
                        raise ValueError(envelope["error"])
                    raise RuntimeError(envelope["error"])
                raise RuntimeError("GLB inspection worker returned invalid response.")
            finally:
                if child.poll() is None:
                    child.kill()
                child.wait()
    finally:
        _SLOTS.release()
