"""Bounded, read-only mesh inspection. Counts do not certify model validity."""

from __future__ import annotations

import codecs
import hashlib
import io
import math
import os
import struct
from pathlib import Path

from .glb import inspect_glb
from .glb_isolation import inspect_isolated
from .obj_records import obj_records
from .paths import root_path, source_path

MAX_PREVIEW_BYTES = 128 * 1024 * 1024
MAX_VERTICES = 1_000_000
MAX_FACES = 2_000_000


def _sha256(stream, length: int) -> str:
    digest = hashlib.sha256()
    remaining = length
    while remaining:
        chunk = stream.read(min(remaining, 1024 * 1024))
        if not chunk:
            raise ValueError("Source file changed during inspection.")
        digest.update(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def _lines(stream, length: int, encoding: str):
    decoder = io.IncrementalNewlineDecoder(codecs.getincrementaldecoder(encoding)(), translate=True)
    pending = []
    remaining = length
    while remaining:
        raw = stream.read(min(remaining, 64 * 1024))
        if not raw:
            raise ValueError("Source file changed during inspection.")
        remaining -= len(raw)
        lines = decoder.decode(raw, final=not remaining).split("\n")
        pending.append(lines[0])
        if len(lines) > 1:
            yield "".join(pending)
            yield from lines[1:-1]
            pending = [lines[-1]]
    if tail := "".join(pending):
        yield tail


def _signature(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _bounds(vertices: list[tuple[float, float, float]]) -> dict | None:
    if not vertices:
        return None
    return {
        "min": [min(point[i] for point in vertices) for i in range(3)],
        "max": [max(point[i] for point in vertices) for i in range(3)],
    }


def _stl(stream, length: int) -> dict:
    header = stream.read(min(84, length))
    if len(header) == 84:
        triangles = struct.unpack_from("<I", header, 80)[0]
        if length == 84 + 50 * triangles:
            if triangles == 0:
                raise ValueError("STL contains no triangles.")
            box_min = [math.inf] * 3
            box_max = [-math.inf] * 3
            for _ in range(triangles):
                record = stream.read(50)
                if len(record) != 50:
                    raise ValueError("Source file changed during inspection.")
                coords = struct.unpack_from("<9f", record, 12)
                if not all(math.isfinite(v) for v in coords):
                    raise ValueError("Binary STL contains non-finite vertex coordinates.")
                for axis in range(3):
                    for value in coords[axis::3]:
                        box_min[axis] = min(box_min[axis], value)
                        box_max[axis] = max(box_max[axis], value)
            return {"encoding": "binary", "triangles": triangles, "bounds": {"min": box_min, "max": box_max}}
    stream.seek(0)
    try:
        return _ascii_stl(_lines(stream, length, "utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("Invalid STL: neither consistent binary nor UTF-8 ASCII.") from exc


def _coordinates(tokens, description):
    try:
        values = tuple(float(value) for value in tokens)
    except ValueError as exc:
        raise ValueError(f"Invalid ASCII STL {description}.") from exc
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"ASCII STL contains non-finite {description} coordinates.")
    return values


def _ascii_stl(lines) -> dict:
    records = (parts for line in lines if (parts := line.split()))
    first = next(records, [])
    if not first or first[0].lower() != "solid":
        raise ValueError("Invalid ASCII STL framing.")
    box_min = [math.inf] * 3
    box_max = [-math.inf] * 3
    facets = 0
    inside = False
    ended = False
    facet_vertices = 0
    for parts in records:
        kind = parts[0].lower()
        if ended:
            raise ValueError("Invalid ASCII STL framing.")
        if kind == "endsolid":
            ended = True
        elif kind == "facet":
            if inside or len(parts) != 5 or parts[1].lower() != "normal":
                raise ValueError("Invalid ASCII STL facet.")
            _coordinates(parts[2:], "normal")
            inside, facet_vertices = True, 0
        elif kind == "vertex":
            if not inside or len(parts) != 4:
                raise ValueError("Vertex found outside an ASCII STL facet.")
            point = _coordinates(parts[1:], "vertex")
            for axis, value in enumerate(point):
                box_min[axis] = min(box_min[axis], value)
                box_max[axis] = max(box_max[axis], value)
            facet_vertices += 1
            if facet_vertices > 3:
                raise ValueError("ASCII STL facet contains too many vertices.")
        elif kind == "endfacet":
            if not inside or facet_vertices != 3:
                raise ValueError("Incomplete ASCII STL facet.")
            inside = False
            facets += 1
        elif kind not in {"outer", "endloop"}:
            raise ValueError("Unexpected ASCII STL token.")
    if not ended:
        raise ValueError("Invalid ASCII STL framing.")
    if inside or not facets:
        raise ValueError("Incomplete ASCII STL geometry.")
    return {"encoding": "ascii", "triangles": facets, "bounds": {"min": box_min, "max": box_max}}


def _obj(lines) -> dict:
    vertices: list[tuple[float, float, float]] = []
    faces = 0
    for line in obj_records(lines):
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v":
            if len(parts) < 4 or len(vertices) >= MAX_VERTICES:
                raise ValueError("Invalid OBJ vertex or vertex count limit exceeded.")
            try:
                point = tuple(float(x) for x in parts[1:4])
            except ValueError as exc:
                raise ValueError("Invalid OBJ vertex.") from exc
            if not all(math.isfinite(v) for v in point):
                raise ValueError("OBJ contains non-finite coordinates.")
            vertices.append(point)
        elif parts[0] == "f":
            if len(parts) < 4 or faces >= MAX_FACES:
                raise ValueError("Invalid OBJ face or face count limit exceeded.")
            for token in parts[1:]:
                vertex_ref = token.split("/")[0]
                try:
                    index = int(vertex_ref)
                except ValueError as exc:
                    raise ValueError("Invalid OBJ vertex reference.") from exc
                if index == 0 or (index > 0 and index > len(vertices)) or (
                    index < 0 and -index > len(vertices)
                ):
                    raise ValueError("OBJ face references a missing vertex.")
            faces += 1
    if not vertices or not faces:
        raise ValueError("OBJ contains no mesh geometry.")
    return {"vertices": len(vertices), "faces": faces, "bounds": _bounds(vertices)}


def inspect_mesh(stream, length: int, suffix: str) -> dict:
    if suffix == ".stl":
        return _stl(stream, length)
    if suffix == ".glb":
        return inspect_glb(stream, length)
    return _obj(_lines(stream, length, "utf-8-sig"))


def inspect_asset(path: str | Path, workspace: str | Path = ".", *, cancelled=None) -> dict:
    root = root_path(workspace)
    source = source_path(path, root)
    if source.suffix.lower() != ".glb":
        return _inspect_asset_local(source, root)
    initial = source.stat()
    if initial.st_size > MAX_PREVIEW_BYTES:
        raise ValueError("File exceeds the inspection size limit.")
    result = inspect_isolated(source, root, cancelled)
    if _signature(initial) != _signature(source.stat()) or result.get("size_bytes") != initial.st_size:
        raise ValueError("Source file changed during inspection.")
    return result


def _inspect_asset_local(path: str | Path, workspace: str | Path = ".") -> dict:
    root = root_path(workspace)
    source = source_path(path, root)
    suffix = source.suffix.lower()
    initial_path = source.stat()
    with source.open("rb") as stream:
        initial = os.fstat(stream.fileno())
        if initial.st_size != initial_path.st_size or initial.st_mtime_ns != initial_path.st_mtime_ns:
            raise ValueError("Source file changed during inspection.")
        size = initial.st_size
        if size > 512 * 1024 * 1024:
            raise ValueError("File exceeds the metadata inspection size limit.")
        if suffix in {".stl", ".obj", ".glb"} and size > MAX_PREVIEW_BYTES:
            raise ValueError("File exceeds the inspection size limit.")
        info = {
            "name": source.name, "format": suffix[1:],
            "size_bytes": size, "sha256": _sha256(stream, size),
            "inspection": "structure_only",
            "limitations": "Does not prove manifoldness, printability, visual quality or game readiness.",
        }
        stream.seek(0)
        if suffix in {".stl", ".obj", ".glb"}:
            info.update(inspect_mesh(stream, size, suffix))
            if suffix == ".glb":
                info["inspection"] = "embedded_base_geometry"
        else:
            info["limitations"] += " This format has metadata-only inspection without Blender."
        try:
            current = source.stat()
        except FileNotFoundError as exc:
            raise ValueError("Source file changed during inspection.") from exc
        # Windows may report different identity fields for path and descriptor stats.
        if _signature(initial) != _signature(os.fstat(stream.fileno())) or _signature(initial_path) != _signature(current):
            raise ValueError("Source file changed during inspection.")
    return info
