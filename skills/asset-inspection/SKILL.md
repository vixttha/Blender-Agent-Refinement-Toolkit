---
name: asset-inspection
description: Read-only inspection of basic STL, OBJ and embedded GLB geometry and other supported asset metadata.
---

# Asset inspection

Use blender-agent inspect PATH or the MCP inspect_model tool. The source must resolve within the configured workspace.

Implemented: SHA-256 and file size for STL, OBJ, GLB, FBX and BLEND; basic STL triangle counts and bounds; OBJ vertices/faces and bounds.

Development v0.0.3.5 adds embedded GLB triangle, degenerate triangle, encoded vertex, local and scene base bounds, scene-instance and component inventory measurements. It rejects unsupported required extensions, compressed geometry, URI resources, invalid binary geometry and entirely unusable scene-referenced base surfaces. Distinguish encoded counts from welded counts and do not claim full glTF conformance or evaluated geometry. See docs/HARNESS.md for limits.

A successful inspection is not proof of watertightness, wall thickness, rig correctness, collision validity or visual quality.

Test with python -m unittest discover -s tests -v.
