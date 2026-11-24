---
name: procedural-primitives
description: Generate a cube, UV sphere, or cylinder with a fixed Blender operation.
---

# Procedural primitives

Use blender-agent create cube output/cube.stl --size 1. Other valid kinds are uv_sphere and cylinder. Use patched stable Blender 4.5 LTS (4.5.15+) or 5.2 LTS (5.2.3+) within those branches.

The cube uses side length, sphere uses diameter, and cylinder uses diameter and height. Values are Blender scene units; STL does not encode physical units.

This is simple primitive generation, not text-to-3D, sculpting or character design. Check exports in the target application.
