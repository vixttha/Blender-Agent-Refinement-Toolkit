# Architecture — v0.0.2 candidate

Any compatible harness invokes the Python CLI or optional MCP stdio server, both of which call the same implementation:

~~~text
CLI / MCP stdio
       |
Python core
  |-- restricted workspace path guard
  |-- bounded STL/OBJ inspector
  |-- GLB inspector -> resource-limited Python child
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
5. Blender operations must finish successfully and leave a scene with mesh faces before exporting. For STL, OBJ and FBX exports, the worker records the active scene geometry (`pre_export_scene`). BLEND saves and GLB multi-scene exports retain a file-wide source summary (`pre_export_file`); GLB keeps Blender’s default multi-scene export behavior. The file-wide summary can include objects not represented in the exported artifact. Repair traverses the same object scope, processing each distinct editable mesh datablock once. Read-only linked meshes outside the active-scene scope do not block STL, OBJ or FBX repair; an in-scope read-only mesh is rejected without publication. BLEND and GLB repair retain file-wide scope. Both scopes count original mesh datablocks per object before export, not evaluated geometry, instances or independently verified export counts. The host checks published size and structurally inspects staged STL and OBJ files up to 128 MiB. Staged GLB exports require independent embedded base-geometry validation within 128 MiB, with artifact-scoped counts and SHA-256; oversized or unsupported GLB outputs are withheld. FBX, BLEND and larger STL/OBJ files receive a nonempty-file check. The result records the check in `artifact_validation` and reports the size captured from the staged output.
6. Blender subprocess output capture and execution time are bounded; inspection and import/export have explicit size caps. GLB parsing runs in a fixed resource-limited child with a separate deadline, bounded admission and kill/reap cancellation. The host rechecks staged identity and digest before atomic publication. See SECURITY.md and HARNESS.md for platform limits and trust assumptions.

The file guard does not prevent a hostile process with simultaneous write access from renaming or swapping directories during operation. Trust or isolate the workspace at the OS level.

## Validation and support

Pure Python unit tests run on Windows and Linux with Python 3.11 and 3.12. Optional MCP tests use a real stdio client on both OS families. The development CI matrix uses checksum-pinned Blender 4.5.17 and 5.2.5 on Linux and 4.5.17 on Windows, with real installed-wheel MCP fixtures. The branch-aware runtime gate runs before reading the job and returns the effective version in successful CLI/MCP results. See [Harness integration](HARNESS.md#blender-runtime-policy) for exact checks. No compatibility promise is made for Blender builds not tested.

## Future B+C architecture

Permanent hierarchical specialist skills coexist with proposed dynamic skills. Promotion requires evidence and approval; generated skills are not executed in v0.0.2. Shared memory and cloud orchestration are future architecture rather than implemented features.
