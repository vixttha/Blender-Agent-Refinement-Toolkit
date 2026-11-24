"""Trusted static worker executed by Blender, not by the host Python interpreter.

Only fixed, enumerated operations are available; no model-supplied Python is executed.
"""

import json
import sys
from pathlib import Path

# Floors for stable maintained release branches, not a blanket numeric minimum.
# CVE-2026-119722: https://github.com/advisories/GHSA-xrhr-77c8-rr8q
RUNTIME_PATCH_FLOORS = {(4, 5): 15, (5, 2): 3}
RUNTIME_REQUIREMENT = "Use stable Blender 4.5 LTS >= 4.5.15 or 5.2 LTS >= 5.2.3."


def require_runtime(version, cycle):
    """Check Blender's own runtime metadata before reading the job or any asset."""
    if not isinstance(version, tuple) or len(version) != 3 or any(
        type(part) is not int or part < 0 for part in version
    ):
        raise RuntimeError("Unrecognized Blender runtime version. " + RUNTIME_REQUIREMENT)
    label = ".".join(str(part) for part in version)
    floor = RUNTIME_PATCH_FLOORS.get(version[:2])
    if cycle != "release" or floor is None or version[2] < floor:
        raise RuntimeError(f"Unsupported Blender runtime {label} ({cycle}). " + RUNTIME_REQUIREMENT)
    return label


def _clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def _import(path):
    extension = path.suffix.lower()
    if extension == ".blend":
        return bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False, use_scripts=False)
    elif extension == ".stl":
        return bpy.ops.wm.stl_import(filepath=str(path))
    elif extension == ".obj":
        return bpy.ops.wm.obj_import(filepath=str(path))
    elif extension == ".glb":
        return bpy.ops.import_scene.gltf(filepath=str(path))
    elif extension == ".fbx":
        return bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        raise ValueError("Unsupported import format.")


def _export(path):
    extension = path.suffix.lower()
    if extension == ".blend":
        if bpy.data.filepath:
            _require_finished(bpy.ops.file.make_paths_absolute(), "external path anchoring")
        return bpy.ops.wm.save_as_mainfile(filepath=str(path), relative_remap=False)
    elif extension == ".stl":
        return bpy.ops.wm.stl_export(filepath=str(path), export_selected_objects=False)
    elif extension == ".obj":
        return bpy.ops.wm.obj_export(filepath=str(path), export_materials=True)
    elif extension == ".glb":
        return bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB")
    elif extension == ".fbx":
        return bpy.ops.export_scene.fbx(filepath=str(path))
    else:
        raise ValueError("Unsupported export format.")


def _create(kind, size):
    if kind == "cube":
        return bpy.ops.mesh.primitive_cube_add(size=size)
    elif kind == "uv_sphere":
        return bpy.ops.mesh.primitive_uv_sphere_add(radius=size / 2)
    elif kind == "cylinder":
        return bpy.ops.mesh.primitive_cylinder_add(radius=size / 2, depth=size)
    else:
        raise ValueError("Unsupported primitive.")


def _repair(objects):
    repaired = set()
    for obj in objects:
        if obj.type != "MESH":
            continue
        mesh = obj.data
        identity = mesh.as_pointer()
        if identity in repaired:
            continue
        # Blender 4.1 exposes the library but does not expose ID.is_editable.
        if not getattr(mesh, "is_editable", mesh.library is None):
            raise ValueError("Repair requires editable mesh datablocks.")
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.0001)
            if bm.faces:
                bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            bm.to_mesh(mesh)
            mesh.update()
        finally:
            bm.free()
        repaired.add(identity)
    return len(repaired)


def _geometry(objects):
    total = {"mesh_objects": 0, "vertices": 0, "faces": 0,
             "boundary_edges": 0, "nonmanifold_edges": 0}
    for obj in objects:
        if obj.type != "MESH":
            continue
        total["mesh_objects"] += 1
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            total["vertices"] += len(bm.verts)
            total["faces"] += len(bm.faces)
            total["boundary_edges"] += sum(1 for edge in bm.edges if edge.is_boundary)
            total["nonmanifold_edges"] += sum(1 for edge in bm.edges if not edge.is_manifold)
        finally:
            bm.free()
    return total


def _require_finished(status, operation):
    if "FINISHED" not in status:
        raise RuntimeError(f"Blender did not finish {operation}.")


def main():
    global bpy, bmesh
    import bpy
    runtime_version = require_runtime(tuple(bpy.app.version), bpy.app.version_cycle)
    import bmesh
    arguments = sys.argv[sys.argv.index("--") + 1:]
    if len(arguments) != 1:
        raise ValueError("Expected one job manifest path.")
    job = json.loads(Path(arguments[0]).read_text(encoding="utf-8"))
    operation = job["operation"]
    _clear()
    if operation == "create":
        _require_finished(_create(job["kind"], float(job["size"])), "primitive creation")
    elif operation in {"convert", "repair"}:
        _require_finished(_import(Path(job["source"])), "mesh import")
    else:
        raise ValueError("Unknown operation.")
    output = Path(job["output"])
    # BLEND saves the whole file; GLB preserves the default multi-scene export.
    # Other exporters operate on the active scene. These are pre-export counts.
    objects = bpy.data.objects if output.suffix.lower() in {".blend", ".glb"} else bpy.context.scene.objects
    if operation == "repair":
        repaired_meshes = _repair(objects)
    geometry = _geometry(objects)
    if operation == "repair":
        geometry["repaired_mesh_datablocks"] = repaired_meshes
    if geometry["vertices"] < 3 or geometry["faces"] < 1:
        raise ValueError("No mesh faces are available for output.")
    _require_finished(_export(output), "mesh export")
    geometry["blender_version"] = runtime_version
    Path(job["report"]).write_text(json.dumps(geometry), encoding="utf-8")


if __name__ == "__main__":
    main()
