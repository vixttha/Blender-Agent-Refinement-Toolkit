# Adoption evidence

Upstream source pin: [8af9508e20fa80e6dc312ededc83f4a8007ecf92](https://github.com/vixttha/Version-Issues-Hub/commit/8af9508e20fa80e6dc312ededc83f4a8007ecf92); candidate, not a released package. [Passing push workflow](https://github.com/vixttha/Version-Issues-Hub/actions/runs/45330357063) attempt 1: verify and Graphify passed on ubuntu-latest. Newer source 32fd798cce1ec499122bf416adf757ecf695fafa changed no package paths, but its [Graphify job](https://github.com/vixttha/Version-Issues-Hub/actions/runs/45330576882/job/138230539238) failed an exact anchor lookup. Track [BART #106](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues/106). Upstream product enforcement pilot remains open; no live gate configured. This installation uses the exact eight package files selected by upstream installer and host-local ledger/handoff. Package hashes in manifest; source Git blobs:

- `AGENTS.md`: `eb026c9fa7f237ccfebc73d0bddd34e8b2fdb6e2`
- `GATE.md`: `f43ef22449e99dafe8d0a0afab3f6b744f4b53ea`
- `README.md`: `aeec2d03511e8ff69fa9948b9c1b89236b77c612`
- `WORKFLOW.md`: `b78216d797cadca0b07bdf65ae73618cc3df9438`
- `tools/checkpoint.py`: `c7ac5c959820db0c3ee28ab333cb0a1dfac0b8b5`
- `tools/gate.py`: `5faf403070ed0ad294d92f9b20fa49bc7e067553`
- `tools/install.py`: `6ccdf7c9dc0c815fe2c34a538af04e787be20bf1`
- `tools/session.py`: `f483fd632e1990ee592448f50e4f35e5e049a401`

Parent product baseline `3e7f9e02e61739825b56bcafecebbd0221cc9657`; fresh independent tree, no product ref updates. The branch commit is the installed revision. Branch-specific validation checks the pin, identity and current state; it is not product acceptance. Existing [BART Graphify archive](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/tree/graphify-hq) remains separate, not evidence for this installed branch. No new BART asset behavior changed or tested. Solo audit, no independent reviewer claim.
