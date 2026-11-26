"""Fixed subprocess entry point. Run with isolated Python, never on import."""
import json
import os
from pathlib import Path
import sys


def _limit_memory(limit):
    if sys.platform == "linux":
        import resource
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        if hard != resource.RLIM_INFINITY:
            limit = min(limit, hard)
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        return None
    if os.name != "nt":
        raise RuntimeError("GLB worker memory enforcement is unsupported on this platform.")
    import ctypes as c
    from ctypes import wintypes as w

    class Basic(c.Structure):
        _fields_ = [("PerProcessUserTimeLimit", c.c_longlong),
                    ("PerJobUserTimeLimit", c.c_longlong), ("LimitFlags", w.DWORD),
                    ("MinimumWorkingSetSize", c.c_size_t), ("MaximumWorkingSetSize", c.c_size_t),
                    ("ActiveProcessLimit", w.DWORD), ("Affinity", c.c_size_t),
                    ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]

    class IO(c.Structure):
        _fields_ = [(name, c.c_ulonglong) for name in
                    ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                     "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class Extended(c.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IO),
                    ("ProcessMemoryLimit", c.c_size_t), ("JobMemoryLimit", c.c_size_t),
                    ("PeakProcessMemoryUsed", c.c_size_t), ("PeakJobMemoryUsed", c.c_size_t)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.AssignProcessToJobObject.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise RuntimeError("GLB worker could not establish its memory limit.")
    info = Extended()
    info.BasicLimitInformation.LimitFlags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.ProcessMemoryLimit = limit
    if not kernel.SetInformationJobObject(job, 9, c.byref(info), c.sizeof(info)) or not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        kernel.CloseHandle(job)
        raise RuntimeError("GLB worker could not establish its memory limit.")
    # Keep the non-inheritable job handle alive until process termination.
    return job


def main():
    # -I -S ignores cwd, PYTHONPATH and user/site startup hooks. Admit only
    # the package directory containing this fixed worker.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from blender_agent.glb_isolation import MEMORY_BYTES, MAX_RESPONSE_BYTES
    try:
        job = _limit_memory(MEMORY_BYTES)
        from blender_agent.inspect import _inspect_asset_local
        source, root = sys.argv[1:]
        result = _inspect_asset_local(source, root)
        envelope = {"ok": True, "result": result}
    except ValueError as exc:
        envelope = {"ok": False, "kind": "invalid", "error": str(exc)[:1024]}
    except (OSError, RuntimeError, MemoryError) as exc:
        envelope = {"ok": False, "kind": "worker", "error": "GLB worker resource or I/O failure: " + str(exc)[:1024]}
    raw = json.dumps(envelope, allow_nan=False, ensure_ascii=True).encode("ascii")
    if len(raw) > MAX_RESPONSE_BYTES:
        raw = b'{"ok":false,"kind":"worker","error":"GLB worker response exceeds its limit."}'
    sys.stdout.buffer.write(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
