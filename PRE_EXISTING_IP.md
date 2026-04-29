# Pre-existing Intellectual Property Declaration

> **Purpose**: This document is a tamper-evident timestamped declaration that the
> work in this repository constitutes pre-existing personal intellectual property
> of the Primary Author, authored prior to and independent of any current or
> future employment relationship.

## Repository Identification

- **Repository**: [hibou04-ops/mini-omega-lock](https://github.com/hibou04-ops/mini-omega-lock)
- **License**: Apache License 2.0
- **Primary Author**: **Kyunghoon Gwak (곽경훈)** — operating as [@hibou04-ops](https://github.com/hibou04-ops)
  - Primary email: `hibouaile04@gmail.com` (verified, primary on the GitHub account; the Primary Author's only personal email)
  - Note: some commits in the git history before 2026-04-29 carry `hibou04@gmail.com` in the author email field. That address is **not** an account belonging to the Primary Author — it was an unintended local git client misconfiguration. The author *name* `Hibou04-ops` is the unambiguous identifier across the entire history. From 2026-04-29 onwards every repository in this toolkit is configured to commit under `hibouaile04@gmail.com`.

## Authorship Timeline (Tamper-Evident)

The following git artifacts establish the authorship timeline. The git commit graph
and the public GitHub remote (`github.com/hibou04-ops/mini-omega-lock`) provide
independent timestamp witnesses.

| Anchor | Commit Hash | Date (KST) | Description |
|---|---|---|---|
| First commit | `0baa813` | 2026-04-22 | feat: initial release v0.1.0 — empirical preflight probes for omegaprompt |
| Apache 2.0 relicense | `ff489a9` | 2026-04-22 | MIT → Apache 2.0 for patent grant + trademark preservation |
| 0.2.0 release | `81fd2db` | 2026-04-28 | License MIT->Apache 2.0 PyPI distribution alignment |
| Pre-employment snapshot | (tagged on commit) | 2026-04-29 | This declaration committed; tagged `pre-employment-ip-snapshot-2026-04-29` |

## Scope of Pre-existing IP

The following work product is declared as pre-existing personal intellectual property:

1. **Empirical Preflight Suite**: Probes for live measurement of omegaprompt
   runtime conditions:
   - Judge consistency probe (cross-vendor and intra-vendor agreement)
   - Endpoint schema reliability probe (strict-schema acceptance behaviour)
   - Context-budget margin probe (token-headroom measurement)
   - Latency and noise-floor measurements
2. **Adapter Plumbing**: All code under `src/mini_omega_lock/` mapping probe
   outputs to omegaprompt's `PreflightReport` contract.
3. **Test Suite**: All materials under `tests/`.
4. **Documentation**: README, EASY_README, EASY_README_KR, NOTICE.
5. **Specific Terminology and Application**: The compound term "mini-omega-lock"
   as a sub-tool name within the omegaprompt toolkit. *No claim is made to the
   generic words "omega" or "lock" in isolation; the claim is to the specific
   compound and its application within this corpus.*

## Companion Repositories

This repository is part of a multi-repo IP defense package authored by the same
Primary Author:

- [omegaprompt](https://github.com/hibou04-ops/omegaprompt) — parent calibration framework
- [omega-lock](https://github.com/hibou04-ops/omega-lock) — sensitivity-driven coordinate descent calibration framework
- [Antemortem](https://github.com/hibou04-ops/Antemortem) — pre-implementation reconnaissance methodology
- [antemortem-cli](https://github.com/hibou04-ops/antemortem-cli) — CLI for the Antemortem methodology
- [mini-antemortem-cli](https://github.com/hibou04-ops/mini-antemortem-cli) — analytical sibling preflight tool

See each repository's `PRE_EXISTING_IP.md` for its own authorship binding.

## Development Conditions

This work was developed:

- Using **personal time** (outside of any third-party working hours)
- Using **personal equipment** (no employer-issued hardware)
- Using **personal accounts** (no employer-issued cloud, LLM, or API credentials)
- **Without reference** to any third party's confidential or proprietary information

## Use in Future Employment Agreements

This declaration is intended to be attached as a Schedule / Exhibit (commonly
"Schedule A: Pre-existing IP") to any future employment, contractor, or
consulting agreement, to clarify that:

- The work in this repository remains the personal property of the Primary Author.
- Future development on this codebase, conducted on personal time and outside the
  scope of any employment, continues to be the Primary Author's personal IP.
- Any contributions from a future employer's domain, made on employer time using
  employer resources, would be governed by the relevant employment agreement —
  the boundary is preserved by maintaining a separate repository, fork, or
  branch for any such employer-domain contributions.

## Verification

To independently verify this declaration:

1. Inspect git log:
   ```
   git log --format="%H | %ai | %an <%ae>" | grep "Hibou04-ops"
   ```
2. Confirm tag (when committed):
   ```
   git tag -l "pre-employment-ip-snapshot-*"
   git show pre-employment-ip-snapshot-2026-04-29
   ```
3. Cross-reference with public GitHub timestamps:
   - https://github.com/hibou04-ops/mini-omega-lock/commit/0baa813
   - https://github.com/hibou04-ops/mini-omega-lock/releases

---

**Declaration date**: 2026-04-29
**License**: Apache License 2.0
**Document version**: 1.0
