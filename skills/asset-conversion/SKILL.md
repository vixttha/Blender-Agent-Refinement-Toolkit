---
name: asset-conversion
description: Convert supported asset formats through the fixed headless Blender worker.
---

# Asset conversion

Use blender-agent convert SOURCE DESTINATION. A patched stable Blender runtime must be available: 4.5 LTS at 4.5.15+ or 5.2 LTS at 5.2.3+ within those branches. Supported import/export extensions: STL, OBJ, GLB, FBX, BLEND.

The output must be different from the source and inside the workspace. The destination folder must exist.

Conversions can lose materials, animation, exact units or metadata. Validate in the intended destination application. Real Blender integration is a separate acceptance gate.
