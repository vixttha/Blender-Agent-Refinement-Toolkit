# BART issue-version hub

**Blender-Agent Refinement Toolkit** — Give shape to an idea.

Permanent standalone branch `Version-Issues-Hub`. Do not merge this tree into main. The product is on main; GitHub Issues remains canonical for bug state. The VIB branch records stable issue-version assignments and cooperative handoff state. This is a trial of an unreleased upstream package, not an enabled merge gate.

## Current product cycle

- Package baseline: v0.0.3 ([release](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/releases/tag/v0.0.3)); main `3e7f9e02e61739825b56bcafecebbd0221cc9657`.
- Target: v0.0.4 (proposed); historical v0.0.3.1 branding checkpoint belongs to [#62](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/62). Keep the version unchanged until a separately approved release.
- Next selected application issue: [#55](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/55) — v0.0.3.2, assigned, no active Worker claim. Existing [PR #81](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/pull/81) head `2ec2bd8c660fc05557c70740c203aed2f232e7c5` is a Test Vault candidate, not a main PR. [Prior application CI](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/actions/runs/44513855716) passed ten jobs on that candidate; it must not certify an untested main-targeting revision. Reuse the application repair without importing unrelated templates.
- Follow Head → Worker → Validate → Internal Auditor → Head, one active Worker and one integration lane. Head accepts scope and criteria, records exact candidate and evidence, and obtains explicit owner approval for merge/release. No paid services, local runners or self-hosted runners; use standard free public GitHub runners.
- Product-first priority: geometry accuracy, repair scope, patched runtime, robust inspection, advanced diagnostics, conversion fidelity and creation. Supporting maintenance only when justified.

## Historical mapping reconciliation

The historical mappings in the ledger come from [main CHANGELOG.md](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/blob/3e7f9e02e61739825b56bcafecebbd0221cc9657/CHANGELOG.md), closed GitHub issues and issue #62. Closed historical issues with a documented checkpoint are marked integrated; open historical issues retain their original version and are assigned for reconciliation rather than falsely closed. No VIB-format receipts are fabricated retroactively. v0.0.2.21 was a follow-up publisher checkpoint to #29 (canonical mapping v0.0.2.19); v0.0.2.20 corresponds to #37. Keep historic labels and fix history intact. Existing Test Vault version labels such as #82's v0.0.4.2 are branch-specific, not product version assignments. Unmapped items in the snapshot remain unassigned until Head approves scope. The snapshot is informational; refresh against live GitHub before any decision.

## Files

- [Installation pin](vib-install.json), [upstream entry point](AGENTS.md), [workflow](WORKFLOW.md), [gate guide](GATE.md)
- [Stable issue-version ledger](ledger/issue-versions.json), [handoff](ledger/handoff.json), [GitHub issue snapshot](ledger/github-issues-snapshot.json), [product queue](PRODUCT-QUEUE.md), [adoption evidence](ADOPTION.md)

BART's product instructions remain on their existing branch. Do not modify product refs, issue states, release tags or rulesets as a side effect of VIB adoption.
