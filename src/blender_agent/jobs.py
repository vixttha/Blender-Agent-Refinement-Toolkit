"""Narrow, bounded Blender operations with atomic no-clobber output publication."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

from .blender_worker import require_runtime
from .inspect import MAX_PREVIEW_BYTES, _signature, inspect_asset, inspect_mesh
from .obj_records import obj_records
from .paths import destination_path, root_path, source_path, within_workspace

PRIMITIVES = frozenset({"cube", "uv_sphere", "cylinder"})
DEFAULT_TIMEOUT = 180
MAX_TIMEOUT = 900
MAX_INPUT_BYTES = 512 * 1024 * 1024
MAX_OUTPUT_BYTES = 512 * 1024 * 1024
MAX_LOG_BYTES = 256 * 1024


def _run_blender(command: list[str], cwd: Path, timeout: int) -> str:
    """Read process output incrementally and kill processes exceeding the log cap."""
    chunks: list[bytes] = []
    used = 0
    exceeded = threading.Event()
    process = subprocess.Popen(
        command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert process.stdout is not None

    def drain() -> None:
        nonlocal used
        try:
            while True:
                data = process.stdout.read(8192)
                if not data:
                    break
                used += len(data)
                if used > MAX_LOG_BYTES:
                    exceeded.set()
                    try:
                        process.kill()
                    except OSError:
                        pass
                    break
                chunks.append(data)
        finally:
            process.stdout.close()

    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
    try:
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise RuntimeError("Blender operation exceeded its timeout.") from exc
    finally:
        thread.join(timeout=5)
    if exceeded.is_set():
        raise RuntimeError("Blender output exceeded the log-size safety limit.")
    log = b"".join(chunks).decode("utf-8", errors="replace")[-2000:]
    if code != 0:
        raise RuntimeError("Blender operation failed: " + log)
    return log


def _validate_publication(temp: Path, final: Path, root: Path) -> int:
    if not temp.is_file() or temp.is_symlink():
        raise RuntimeError("Temporary result is not a regular file.")
    size = temp.stat().st_size
    if not 0 < size <= MAX_OUTPUT_BYTES:
        raise RuntimeError("Generated output is empty or exceeds the size limit.")
    if final.parent.is_symlink() or final.parent.resolve() != final.parent:
        raise ValueError("Output directories must not be symlinks.")
    if temp.parent.resolve() != temp.parent:
        raise ValueError("Temporary directory was unexpectedly moved.")
    if final.is_symlink() or within_workspace(final, root) != final:
        raise ValueError("Output path must remain a regular path inside the workspace.")
    if within_workspace(temp, root) != temp:
        raise ValueError("Temporary path changed outside the workspace.")
    return size


def _publish(temp: Path, final: Path, root: Path, *, overwrite: bool) -> None:
    """Create a destination exclusively, or replace it with explicit permission."""
    _validate_publication(temp, final, root)
    if overwrite:
        if final.exists() and not final.is_file():
            raise FileExistsError("Destination is not a regular file.")
        os.replace(temp, final)
    else:
        # No check-then-replace race: an existing name is never overwritten.
        os.link(temp, final)


def _verify_staged_glb(temp, final, root, identity, digest, cancelled):
    # Recheck the original inspected file and hash immediately before atomic
    # publication. The trusted-workspace rule still excludes hostile writers
    # between this check and the rename/link syscall.
    _validate_publication(temp, final, root)
    if _signature(temp.stat()) != identity:
        raise RuntimeError("Staged GLB changed before publication.")
    hashed = hashlib.sha256()
    with temp.open("rb") as stream:
        if _signature(os.fstat(stream.fileno())) != identity:
            raise RuntimeError("Staged GLB changed before publication.")
        remaining = identity[2]
        while remaining:
            _require_active(cancelled)
            data = stream.read(min(remaining, 1024 * 1024))
            if not data:
                raise RuntimeError("Staged GLB changed before publication.")
            hashed.update(data)
            remaining -= len(data)
        if _signature(os.fstat(stream.fileno())) != identity:
            raise RuntimeError("Staged GLB changed before publication.")
    if _signature(temp.stat()) != identity or hashed.hexdigest() != digest:
        raise RuntimeError("Staged GLB changed before publication.")


def _material_libraries(obj: Path):
    with obj.open(encoding="utf-8-sig", errors="surrogateescape") as stream:
        for line in obj_records(stream):
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[0] == "mtllib":
                yield parts[1].strip().removeprefix('"').removesuffix('"')


@contextmanager
def _obj_lock(path: Path):
    if path.is_symlink():
        raise ValueError("OBJ publication lock must be a regular file.")
    with path.open("ab") as stream:
        try:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise FileExistsError("Destination already exists or another OBJ export is publishing it.") from exc
        yield


def _same_file(path: Path, reference: Path) -> bool:
    if path.is_symlink() or reference.is_symlink():
        return False
    try:
        return path.samefile(reference)
    except FileNotFoundError:
        return False


def _clear_obj_journal(journal: Path) -> None:
    # Remove the ready record first so interrupted cleanup can be retried.
    for name in ("output.json", "next.json", "candidate.obj", "candidate.mtl", "previous.mtl", "restore.mtl"):
        (journal / name).unlink(missing_ok=True)
    journal.rmdir()


def _recover_obj(journal: Path, material: Path) -> None:
    if journal.is_symlink():
        raise ValueError("OBJ publication journal must be a regular directory.")
    if not journal.exists():
        return
    record = journal / "output.json"
    if not record.exists():
        _clear_obj_journal(journal)
        return
    info = json.loads(record.read_text(encoding="utf-8"))
    name = info["name"]
    if Path(name).name != name or Path(name).suffix.lower() != ".obj":
        raise RuntimeError("OBJ publication journal contains an invalid output name.")
    output = material.with_name(name)
    if output.with_suffix(".mtl").name.casefold() != material.name.casefold():
        raise RuntimeError("OBJ publication journal does not match this destination.")
    material = output.with_suffix(".mtl")
    candidate, sidecar = journal / "candidate.obj", journal / "candidate.mtl"
    backup = journal / "previous.mtl"
    required = (candidate, sidecar, backup) if info["replaced_material"] else (candidate, sidecar)
    if any(not entry.is_file() or entry.is_symlink() for entry in required):
        raise RuntimeError("OBJ publication journal is incomplete. Retain it for manual recovery.")

    if _same_file(output, candidate):
        if not _same_file(material, sidecar):
            raise RuntimeError("The published OBJ material changed. Retain the journal for manual recovery.")
    elif _same_file(material, sidecar):
        if info["replaced_material"]:
            restore = journal / "restore.mtl"
            if not restore.exists():
                os.link(backup, restore)
            elif not _same_file(restore, backup):
                raise RuntimeError("The material backup changed. Retain the journal for manual recovery.")
            os.replace(restore, material)
        else:
            material.unlink()
    elif info["replaced_material"] and not _same_file(material, backup):
        raise RuntimeError("The destination material changed. Retain the journal for manual recovery.")
    _clear_obj_journal(journal)


def _require_active(cancelled: threading.Event | None) -> None:
    if cancelled is not None and cancelled.is_set():
        raise RuntimeError("Blender job was cancelled before publication.")


def _publish_obj(
    temp: Path, final: Path, root: Path, *, source: Path | None, overwrite: bool,
    cancelled: threading.Event | None = None,
) -> Path:
    """Publish an OBJ pair with filesystem-backed recovery from an interrupted process."""
    material = final.with_suffix(".mtl")
    staged = temp.with_suffix(".mtl")
    size = _validate_publication(temp, final, root)
    if not staged.is_file():
        raise RuntimeError("Blender did not produce the OBJ material library.")
    if size + _validate_publication(staged, material, root) > MAX_OUTPUT_BYTES:
        raise RuntimeError("Combined OBJ and material library exceed the output size limit.")
    if next(_material_libraries(temp), None) != material.name:
        raise RuntimeError("OBJ does not reference its matching material library.")

    key = hashlib.sha256(os.fsencode(material.name.casefold())).hexdigest()
    lock = final.parent / f".blender-agent-obj-{key}.lock"
    journal = lock.with_suffix(".pending")
    with _obj_lock(lock):
        _recover_obj(journal, material)
        _validate_publication(temp, final, root)
        _validate_publication(staged, material, root)
        replaced_material = material.exists()
        if replaced_material:
            if not overwrite or not material.is_file():
                raise FileExistsError("Destination already exists: OBJ material library.")
            if source is not None and source.suffix.lower() == ".obj":
                if source.with_suffix(".mtl").resolve() == material or any(
                    (source.parent / name).resolve() == material for name in _material_libraries(source)
                ):
                    raise ValueError("Source material libraries cannot be modified in place.")

        journal.mkdir()
        try:
            os.link(temp, journal / "candidate.obj")
            os.link(staged, journal / "candidate.mtl")
            if replaced_material:
                os.link(material, journal / "previous.mtl")
            record = journal / "next.json"
            record.write_text(json.dumps({"name": final.name, "replaced_material": replaced_material}), encoding="utf-8")
            os.replace(record, journal / "output.json")
            _require_active(cancelled)
            _publish(staged, material, root, overwrite=replaced_material)
            _publish(temp, final, root, overwrite=overwrite)
        finally:
            _recover_obj(journal, material)
    return material


def validate_timeout(timeout: int) -> None:
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= MAX_TIMEOUT:
        raise ValueError("Timeout must be between 1 and 900 seconds.")


def execute(
    operation: str,
    *,
    workspace: str | Path = ".",
    source: str | Path | None = None,
    output: str | Path,
    kind: str | None = None,
    size: float = 1.0,
    blender: str = "blender",
    overwrite: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    cancelled: threading.Event | None = None,
) -> dict:
    _require_active(cancelled)
    if operation not in {"create", "convert", "repair"}:
        raise ValueError("Unknown operation.")
    validate_timeout(timeout)
    root = root_path(workspace)
    if operation == "create":
        if kind not in PRIMITIVES:
            raise ValueError("Choose cube, uv_sphere, or cylinder.")
        if not isinstance(size, (float, int)) or not math.isfinite(size) or not 0 < size <= 10000:
            raise ValueError("Primitive size must be finite and between 0 and 10000.")
        input_path = None
    else:
        if source is None:
            raise ValueError("Source path is required.")
        input_path = source_path(source, root)
        if input_path.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError("Source file exceeds the size limit.")
    final = destination_path(output, root, source=input_path, overwrite=overwrite)
    if final.parent.is_symlink() or final.parent.resolve() != final.parent:
        raise ValueError("Output directories must not be symlinks.")
    executable = shutil.which(blender)
    if executable is None:
        raise FileNotFoundError("Blender executable not found; configure --blender.")
    executable = os.path.abspath(executable)
    worker = Path(__file__).with_name("blender_worker.py")
    with tempfile.TemporaryDirectory(prefix=".blender-agent-", dir=final.parent) as directory:
        temporary = Path(directory) / final.name
        report = Path(directory) / "report.json"
        job = Path(directory) / "job.json"
        job.write_text(json.dumps({
            "operation": operation,
            "source": str(input_path) if input_path else None,
            "output": str(temporary),
            "report": str(report),
            "kind": kind,
            "size": size,
        }), encoding="utf-8")
        command = [
            executable, "--background", "--factory-startup", "--disable-autoexec",
            "--python-exit-code", "17", "--python", str(worker), "--", str(job),
        ]
        _run_blender(command, cwd=root, timeout=timeout)
        _require_active(cancelled)
        if not temporary.is_file() or not report.is_file():
            raise RuntimeError("Blender did not produce the output and geometry report.")
        size = _validate_publication(temporary, final, root)
        details = json.loads(report.read_text(encoding="utf-8"))
        if (not isinstance(details, dict) or details.get("mesh_objects", 0) < 1
                or details.get("vertices", 0) < 3 or details.get("faces", 0) < 1):
            raise RuntimeError("Blender geometry report is incomplete.")
        blender_version = details.pop("blender_version", None)
        try:
            if not isinstance(blender_version, str) or len(blender_version) > 32:
                raise ValueError("Missing runtime version")
            reported = require_runtime(tuple(int(part) for part in blender_version.split(".")), "release")
            if reported != blender_version:
                raise ValueError("Noncanonical runtime version")
        except (ValueError, RuntimeError) as exc:
            raise RuntimeError("Blender runtime report is missing or unsupported.") from exc
        artifact_validation = "nonempty_file"
        suffix = final.suffix.lower()
        if suffix in {".stl", ".obj"} and size <= MAX_PREVIEW_BYTES:
            with temporary.open("rb") as stream:
                inspect_mesh(stream, size, suffix)
            artifact_validation = "structural_mesh"
        artifact_geometry = None
        artifact_sha256 = None
        if suffix == ".glb":
            staged_identity = _signature(temporary.stat())
            artifact_geometry = inspect_asset(temporary, root, cancelled=cancelled)
            if artifact_geometry["size_bytes"] != size:
                raise RuntimeError("Staged GLB size changed before publication.")
            artifact_sha256 = artifact_geometry.pop("sha256")
            artifact_geometry.pop("name")
            artifact_validation = "glb_embedded_base_geometry"
        material = None
        if suffix == ".obj":
            material = _publish_obj(
                temporary, final, root, source=input_path, overwrite=overwrite, cancelled=cancelled,
            )
        else:
            _require_active(cancelled)
            if artifact_sha256 is not None:
                _verify_staged_glb(temporary, final, root, staged_identity, artifact_sha256, cancelled)
            _require_active(cancelled)
            _publish(temporary, final, root, overwrite=overwrite)
    result = {
        "ok": True, "operation": operation, "output": str(final.relative_to(root)),
        "size_bytes": size, "geometry": details,
        "blender_version": blender_version,
        "geometry_scope": "pre_export_file" if suffix in {".blend", ".glb"} else "pre_export_scene",
        "artifact_validation": artifact_validation,
        "note": "Geometry summary only; not a production or printability certification.",
    }
    if artifact_geometry is not None:
        result["artifact_geometry"] = artifact_geometry
        result["artifact_sha256"] = artifact_sha256
    if material is not None:
        result["material_library"] = str(material.relative_to(root))
    return result
