# Security

This project reads third-party 3D formats and may launch Blender. **Treat externally supplied models and BLEND projects as untrusted.** The path rules are safeguards, not OS isolation.

## Defensive controls

- Inputs and outputs are restricted to a configured, resolved workspace root.
- A source file can never be its own output path; existing outputs are not overwritten unless the CLI explicitly opts in.
- Publication without overwrite uses atomic hard-link creation: concurrent writes cannot silently clobber the same destination.
- The output parent and temporary path are revalidated before publication. Untrusted processes must not concurrently mutate workspace paths or symlinks; use separate OS-level sandboxes for hostile multi-tenant execution.
- Blender runs a fixed worker under background/factory startup with auto-execution disabled; tools do not accept arbitrary generated scripts.
- Before reading a job manifest or importing an asset, the development worker rejects runtimes outside stable 4.5 LTS at patch 15 or newer and stable 5.2 LTS at patch 3 or newer within those branches ([CVE-2026-119722](https://github.com/advisories/GHSA-xrhr-77c8-rr8q)). The caller must configure a trusted executable. The gate is not a sandbox, executable authentication or protection against future Blender vulnerabilities; use current patches and OS isolation. The released v0.0.3 did not enforce this gate.
- Blender work has a bounded timeout (default 180 seconds, maximum 900), captured log budget (256 KiB), input cap (512 MiB), and publication cap (512 MiB). Blender can use more temporary disk space while exporting. Detailed STL/OBJ inspection is limited to 128 MiB and checks whether the source changed during inspection.
- Development GLB inspection/validation rejects URI buffers and images, required extensions, known compressed geometry and GPU instancing; it never resolves external resources. The GLB container is limited to 128 MiB, JSON to 4 MiB, records to 50,000 per collection, JSON depth to 64 and items to 500,000, decoded position visits to 2 million, index visits to 6 million, sparse overrides to 250,000 and transformed position visits to 4 million per inspection. The public GLB inspection and staged validation paths additionally use a fixed isolated Python subprocess, a 60-second wall deadline, a 512 MiB Linux address-space or Windows process commit limit, a 256 KiB response cap and at most two parser children per host process. Unsupported memory-control platforms (including macOS in this checkpoint) or failed memory-limit setup reject detailed GLB inspection. Cancellation kills and reaps an active parser; MCP admits one read-only inspection at a time and rejects contention without queuing. These are resource controls, not a filesystem/network sandbox. The same workspace trust assumptions apply; this does not constrain Blender import of other files or secondary resources.
- GLB staged identity and SHA-256 are rechecked immediately before atomic publication; a mismatch withholds output. This does not protect against a hostile same-account writer racing the final syscall. The parser deadline is separate from the Blender subprocess timeout. Non-GLB parsing is unchanged.
- ASCII STL inspection validates finite normals and triangle vertices. It treats loop markers as optional and skips them while checking each facet.
- Input parsers reject non-finite coordinates and invalid OBJ vertex references; these checks do not validate entire geometry.

## Residual risks

Operating system process memory, Blender add-ons and importer vulnerabilities, hostile directory rename races, and source mutations during import are not comprehensively sandboxed. Never run this process with elevated privileges or on a shared hostile workspace. Untrusted workloads should use a true OS/container boundary. No network service is provided.

The workspace guard applies to the source and destination paths passed to Blender-Agent Refinement Toolkit and the files it publishes. Blender resolves secondary resources such as OBJ material libraries and textures, project images, and linked Blender libraries with the filesystem permissions of its process. Keep those dependencies in a trusted workspace and use OS-level isolation to enforce a stricter read boundary. OBJ publication manages the matching MTL file. Other linked resources must remain available where the asset references them.

## Responsible reporting

Use GitHub private vulnerability reporting if the repository enables it. If unavailable, request a private channel without posting exploit material in a public issue.

Blender-Agent Refinement Toolkit is pre-alpha and carries no established security-support commitment.
