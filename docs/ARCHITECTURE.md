# Architecture — v0.0.2 candidate

Any compatible harness invokes the Python CLI or optional MCP stdio server, both of which call the same implementation:

~~~text
CLI / MCP stdio
       |
Python core
  |-- restricted workspace path guard
  |-- bounded STL/OBJ inspector
  |-- bounded job orchestrator -> fixed headless Blender worker
  |                                  |
  |                     temp output + geometry report
  |                                  |
  |                     atomic no-clobber promotion
  |
future: skill orchestration, memory, more engines
~~~

## Safety invariants

1. Source paths remain inside the workspace and are never used as the output path.
2. Output paths are resolved inside the workspace, checked again before publication, and existing outputs are protected by an atomic hard-link operation when overwrite is disabled.
3. A caller must explicitly opt into overwrite using the CLI; the MCP adapter has no overwrite flag.
4. No agent-provided Python or shell is executed. Blender receives a fixed worker with a job manifest containing an enumerated operation.
5. Blender operations must finish successfully and leave a scene with mesh faces before exporting. For STL, OBJ and FBX exports, the worker records the active scene geometry (`pre_export_scene`). BLEND saves and GLB multi-scene exports retain a file-wide source summary (`pre_export_file`); GLB keeps Blender’s default multi-scene export behavior. The file-wide summary can include objects not represented in the exported artifact. Repair traverses the same object scope, processing each distinct editable mesh datablock once. Read-only linked meshes outside the active-scene scope do not block STL, OBJ or FBX repair; an in-scope read-only mesh is rejected without publication. BLEND and GLB repair retain file-wide scope. Both scopes count original mesh datablocks per object before export, not evaluated geometry, instances or independently verified export counts. The host checks published size and structurally inspects staged STL and OBJ files up to 128 MiB. Other formats and larger files receive a nonempty-file check. The result records the check in `artifact_validation` and reports the size captured from the staged output.
6. Blender subprocess output capture and execution time are bounded; inspection and import/export have explicit size caps.

The file guard does not prevent a hostile process with simultaneous write access from renaming or swapping directories during operation. Trust or isolate the workspace at the OS level.

## Validation and support

Pure Python unit tests run on Windows and Linux with Python 3.11 and 3.12. Optional MCP tests use a real stdio client on both OS families. Blender 4.5.0 integration tests cover creates, repairs, conversion roundtrips, geometry counts, and bounding dimensions on Linux. No compatibility promise is made for Blender builds not tested.

## Future B+C architecture

Permanent hierarchical specialist skills coexist with proposed dynamic skills. Promotion requires evidence and approval; generated skills are not executed in v0.0.2. Shared memory and cloud orchestration are future architecture rather than implemented features.
