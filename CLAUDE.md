# CLAUDE.md — vc-modules

Context for Claude Code working in this repo. Keep it loaded; it encodes the non-obvious rules that
are expensive to rediscover.

## What this repo is
`vc-modules` is the Virto Commerce **module registry + Stable bundle registry** — NOT the platform or
a module's source. It publishes which platform/module versions make up each release channel.

- `bundles/v*/package.json` — the **Stable** bundles (one folder per stable line; `v15` is current).
- `bundles/latest/package.json` — the rolling latest pointer. `bundles/stable.json` maps `"N"` → bundle URL.
- `modules_v3.json` — the **Edge/Alfa** module registry (every module's versions + dependencies). `modules.json` is the legacy v2.
- `pbc/*.json` — Packaged Business Capability groupings.
- `src/` — the **release tooling** (Python + PowerShell). `bundles/RELEASE_PROCEDURE.md` is the canonical how-to.

The actual code lives in **sibling repos** under the monorepo root (`monorepoRoot` in the config):
`vc-platform` + ~117 `vc-module-*`, plus a `local-nuget` feed.

## Release model
Three channels: **Alfa** (bleeding edge), **Edge** (`modules_v3.json`), **Stable** (`bundles/vN`).
Cutting a stable = promoting the platform + ~54 modules to a new dependency-ordered, audited release.

## Cutting a stable release
Use the **`vc-stable-release` skill** and follow **[bundles/RELEASE_PROCEDURE.md](bundles/RELEASE_PROCEDURE.md)**.
Everything version/path-specific is in **[src/release.config.json](src/release.config.json)** —
edit that, not the scripts. Tools read it via `src/config.py` (Python) and
`src/release-config.ps1` (PowerShell).

## Invariants — do not violate
- **Registry edits go on a branch off `master`.** This repo's `dev` is a stale ~14k-commit branch with
  no `bundles/`; never branch from it.
- **Local-first**: build against `local-nuget`, **zero pushes** until the whole bundle is green locally.
- **Obsolete-removal policy**: remove `[Obsolete]` with **no `DiagnosticId`** or `DiagnosticId`
  **`VC0001`–`VC0011`** (`< VC0012`); **keep `VC0012+`**.
- **`TreatWarningsAsErrors=true`** in source repos ⇒ obsolete *usage* of a kept member is a build
  error (this is what forces the `ICancellationToken`→`CancellationToken`,
  `IModuleCatalog`→`IModuleService`, `ModuleBootstrapper.Instance`→`IHasModuleService` migrations).
- **Wave order = platform first, then topological** (`compute_waves.py`); a wave builds against earlier
  waves' freshly packed `local-nuget` outputs.
- **Surface, don't auto-perform** risky/architectural changes (cascading public-API removals, anything
  that breaks downstream + tests) — report and let the user decide.

## Tooling (`src/`) — read the docstrings
`audit_obsolete.py` (Step-0 inventory) · `platform_package_reference.py` · `compute_waves.py` ·
`finalize_bundle.py` · `collect_releases_md.py` (release notes) · `release_module.ps1` (per-module
orchestrator) · `migrate_ict.ps1`. The consumer upgrade script ships per-bundle as
`bundles/vN/update-to-stable.ps1`; the guide is `bundles/vN/update_path.md`.

## Environment / gotchas
- Windows + PowerShell 7. The `bundles/v*` deliverable folders are currently **untracked** in git —
  `git diff` won't show changes to them; don't rely on it to detect edits.
- Some `src` generators are **not idempotent against live state**: `audit_obsolete.py` and
  `finalize_bundle.py` read the *current* sibling-repo sources, so re-running them after the release's
  removals/bumps changes their output. Don't re-run them as a "regression check" once work has started.
- PowerShell pitfalls (learned the hard way): passing a `@{}` hashtable via `pwsh -File` stringifies it
  — build it inside `-Command` or dot-source instead; bash `/tmp` ≠ pwsh `/tmp` (pwsh reads `C:\tmp`);
  prefer `Set-Content -Path X -Value Y` over positional binding.
- End-to-end validation suite: [`vc-testing-module`](https://github.com/VirtoCommerce/vc-testing-module)
  (Playwright + pytest); needs `--import-mode=importlib` and exclude `destructive`/`optional`.
