# Product-first issue queue

Live GitHub is authoritative. The snapshot includes 60 issues (42 open, 18 closed). Pull requests excluded. No issue closure, reassignment or new implementation is implied.

## Product / application priority

- [#55](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/55) — Align geometry reporting with multi-scene Blender projects — v0.0.3.2
- [#69](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/69) — Scope mesh repair to exported geometry when an inactive scene has linked data — unassigned
- [#45](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/45) — Validate and enforce a patched Blender runtime for third-party projects — unassigned
- [#92](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/92) — [Full-stack audit] Reject non-finite binary STL facet normals during structural inspection — unassigned
- [#64](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/64) — Reject malformed ASCII STL loop framing during inspection — unassigned
- [#65](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/65) — Accept trailing OBJ face comments in structural inspection — unassigned
- [#68](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/68) — Handle or clearly report non-UTF-8 comments in OBJ inspection — unassigned
- [#14](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/14) — Reject empty mesh results and distinguish scene geometry from export validation — v0.0.2.7
- [#19](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/19) — Preserve linked assets when publishing a Blender project from staging — v0.0.2.10
- [#23](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/23) — Recover interrupted OBJ and MTL publication without discarding existing assets — v0.0.2.13
- [#20](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/20) — Define the Blender workspace policy for linked asset dependencies — v0.0.2.9
- [#56](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/56) — Explain the trust boundary for exported BLEND projects — unassigned
- [#49](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/49) — Raise the setuptools build minimum to a patched version — unassigned
- [#47](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/47) — Verify active MCP cancellation through real Blender on Windows — unassigned
- [#46](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/46) — Add redacted job diagnostics for Blender execution and recovery — unassigned
- [#31](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/31) — Fix MCP startup at the declared SDK minimum — v0.0.2.17
- [#15](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/15) — Make the tested Blender, Python, and MCP compatibility matrix reproducible — v0.0.2.12
- [#48](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/48) — Document Blender incident response and verify private reporting intake — unassigned
- [#91](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/91) — [Black Team] Disable Git credential persistence for Python and Blender roundtrip jobs — unassigned

## Release and security readiness

- [#29](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/29) — Tie future release publication jobs to an explicit approval for the target SHA
- [#50](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/50) — Enforce the existing PR and CI policy on main
- [#51](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/51) — Require the expected CI jobs in the release approval check
- [#52](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/52) — Archive sanitized test and release approval receipts
- [#53](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/53) — Make interrupted prerelease publication recoverable
- [#90](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/90) — [White Team] Enforce BART's public-only runner policy at job admission

## Supporting infrastructure and branding (secondary)

- [#28](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/28) — Include tracked file modes in Code Stack archive identity checks
- [#62](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/62) — Rebrand as Blender-Agent Refinement Toolkit and lock BART as the agent name
- [#66](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/66) — Make Graphify archive verification tolerate the repository rename
- [#75](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/75) — [Graphify HQ] Keep graph and receipt consistent when writing an evidence map fails
- [#82](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/82) — v0.0.4.2 — Record the observed BLENDER-001 failure in the Vault plan
- [#83](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/83) — [Red Team] Publish the current passing BLENDER-001 result in the Vault plan
- [#84](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/84) — [Red Team] Distinguish truncated PR history from an absent historical Graphify source
- [#85](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/85) — [Red Team] Preserve existing Graphify evidence when the recovery journal is incomplete
- [#86](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/86) — [Blue Team] Record early failures and blocked cases in BART's Vault summary
- [#87](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/87) — Use physical source lines and ordinary Git files for Graphify citations
- [#88](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/88) — [Purple Team] Use the same file-type rules for Graphify publication and archive readback
- [#89](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/89) — Update BART’s maintained Graphify HQ kit references to Veraphifiy
- [#93](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/93) — Staging can accept a cached source commit that is absent from the requested origin
- [#94](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/94) — [Red Team] Verify exact Graphify MCP feature targets before accepting candidate maps
- [#96](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/96) — [Red Team] Verify wheel hashes in the maintained BART Graphify workflow
- [#99](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/99) — [Red Team Dev] Require tracked copied helpers before a BART receipt can attest to its checkout
- [#106](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/106) — VIB adoption: verify upstream Graphify evidence anchor before upgrading the installed pin
