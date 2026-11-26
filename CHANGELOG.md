# Changelog

## v0.0.3.5 — development checkpoint

- Add bounded Python-only embedded GLB base geometry inspection and pre-publication validation, with independent artifact geometry and digest distinct from worker source counts (#114, successor to #14). Preserve the historical published v0.0.3 package and existing runtime safety.
- Isolate GLB parsing on Linux/Windows with memory, deadline, response and concurrency bounds; kill and reap cancelled parsers, verify staged digest again before publication, and preserve precision across composed scene transforms (#114).

## v0.0.3.4 — development checkpoint

- Require patched stable Blender 4.5 LTS (4.5.15+) or 5.2 LTS (5.2.3+) before any Blender operation, expose the effective runtime version, and validate current LTS builds with benign fixtures (#45).

## v0.0.3.3 — development checkpoint

- Scope repair to the existing pre-export geometry selection, so inactive linked reference scenes do not prevent active-scene mesh repair. Retain rejection of in-scope read-only meshes and file-wide BLEND/GLB repair (#69).

## v0.0.3.2 — development checkpoint

- Align pre-export geometry reporting with active-scene STL, OBJ and FBX exports and file-wide BLEND and GLB exports (#55). Preserve GLB multi-scene behavior and distinguish source geometry from artifact validation.

## v0.0.3.1 — branding checkpoint

- Record **Blender-Agent Refinement Toolkit** as the locked product name and **BART** as the locked agent name.
- Apply README v0.0.4 branding and use the renamed repository in the walkthrough and project links.

## v0.0.3 — pre-alpha

- Publish OBJ files with their matching material libraries. Preserve source assets and handle destination collisions and interrupted publication.
- Keep linked Blender resources accessible when saving a project. Repair shared editable meshes once, and reject empty or invalid mesh results.
- Improve structural STL and OBJ inspection, executable resolution, and explicit MCP workspace configuration. Keep MCP responsive while Blender runs and prevent cancelled jobs from publishing when cancellation takes effect before publication.
- Verify installed-wheel MCP workflows on public Ubuntu runners with Blender 4.1.0 and 4.5.0, and on Windows with Blender 4.5.0. The optional MCP adapter requires SDK 1.30 or later in the v1 series.
- Verify the release tag, final default-branch commit, and successful push CI before publishing.

## v0.0.2.21 — v0.0.3 development checkpoint

- Wire the release verifier into an explicitly opted-in publisher and require a live pull-request event to be rejected on public CI.

## v0.0.2.20 — v0.0.3 development checkpoint

- Force the download failure in the Blender 4.5 Ubuntu pull-request job, verify the mirrored archive, and distinguish download and checksum failures.

## v0.0.2.19 — v0.0.3 development checkpoint

- Add a read-only owner-dispatch check that binds the final release tag and SHA to successful exact-commit application CI (#29).

## v0.0.2.18 — v0.0.3 development checkpoint

- Detach the Blender child from the host stdin pipe and verify the installed-wheel MCP workflow with tool-level evidence on the Windows runner (#33).

## v0.0.2.17 — v0.0.3 development checkpoint

- Raise the MCP SDK minimum to 1.30.0 and verify both minimum and normal-resolver wheel installs with real Blender (#31).

## v0.0.2.16 — v0.0.3 development checkpoint

- Restore the Blender 4.1 repair path and validate the full installed-wheel fixture on Blender 4.1.0 and 4.5.0 (#32).

## v0.0.2.15 — v0.0.3 development checkpoint

- Cancel queued or active MCP Blender publications before the commit point and verify that the next request still succeeds (#34).

## v0.0.2.14 — v0.0.3 development checkpoint

- Protect existing source material libraries named by continued OBJ records and share parsing with OBJ inspection (PR #17 audit follow-up).

## v0.0.2.13 — v0.0.3 development checkpoint

- Recover interrupted OBJ and MTL publication with an OS-backed lock and a retained material backup, preserving unrelated files (#23).

## v0.0.2.12 — v0.0.3 development checkpoint

- Run the MCP matrix and real Blender fixture from clean wheel installs with a pinned SDK and recorded platform details (#15).

## v0.0.2.11 — v0.0.3 development checkpoint

- Repair shared editable Blender mesh datablocks once and verify that instance transforms, material assignments, and UVs survive (#22).

## v0.0.2.10 — v0.0.3 development checkpoint

- Anchor BLEND dependencies to the original project and verify a published project still loads a relative image (#19).

## v0.0.2.9 — v0.0.3 development checkpoint

- Document the workspace policy for secondary asset dependencies and explicitly disable script execution when opening Blender projects (#20).

## v0.0.2.8 — v0.0.3 development checkpoint

- Run Blender jobs on a single dedicated worker and verify protocol responsiveness and timeout cleanup on the public Blender runner (#21).

## v0.0.2.7 — v0.0.3 development checkpoint

- Require successful Blender operations and mesh faces, validate staged STL and OBJ files within the inspection limit, and label scene geometry and staged artifact metadata (#14).

## v0.0.2.6 — v0.0.3 development checkpoint

- Accept continued OBJ polygons while rejecting incomplete continuation records and retaining input limits (#24).

## v0.0.2.5 — v0.0.3 development checkpoint

- Stream ASCII STL counts and bounds, detect file changes during inspection, and clarify temporary export disk use (#13).

## v0.0.2.4 — v0.0.3 development checkpoint

- Require setuptools 77.0.3 or later and verify an MIT-licensed wheel built with the minimum backend (#25).

## v0.0.2.3 — v0.0.3 development checkpoint

- Require an explicit MCP workspace and honor the CLI workspace, Blender executable, and timeout flags (#12).

## v0.0.2.2 — v0.0.3 development checkpoint

- Resolve the Blender executable against the launch directory before entering the configured workspace (#18).

## v0.0.2.1 — v0.0.3 development checkpoint

- Preserve the matching MTL file when publishing an OBJ. CLI and MCP results include its workspace-relative path.
- Exercise create, convert, repair, and inspect through MCP with Blender, including a colored OBJ roundtrip and separate OBJ and MTL collision checks.

## v0.0.2 — audited pre-alpha foundation

- Repair the default output overwrite race using atomic no-clobber publication; add simultaneous-writer negative regression tests.
- Recheck workspace containment before output publication and document remaining filesystem threat assumptions.
- Bound Blender process logs, runtime and file sizes; add oversized-input/output and timeout tests.
- Validate structural OBJ face references and strengthen malformed STL/OBJ inputs.
- Verify the installed MCP launcher, handshake, tool schemas and workspace isolation on free GitHub-hosted Linux and Windows runners.
- Expand real Blender format roundtrips and verify mesh geometry, not only output existence.
- Correct version number and prior documentation claims; keep the six-audit-finding evidence explicit.

## v0.0.1 — original pre-alpha foundation candidate (not separately released)

- Python CLI, optional MCP stdio adapter, STL/OBJ inspection, Blender primitive creation, conversion and limited repair.
- Four starter skill documents, README, security and contribution guidance, public-runner CI.
- No general-purpose autonomous modeling, shared memory, or dynamic skill execution.
