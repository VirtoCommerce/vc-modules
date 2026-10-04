# CLAUDE.md — vc-modules

Context for Claude Code working in this repo. Keep it loaded; it encodes the non-obvious rules that
are expensive to rediscover.

## What this repo is
`vc-modules` is the Virto Commerce **module registry + Stable bundle registry** — NOT the platform or
a module's source. It publishes which platform/module versions make up each release channel.

- `bundles/v*/package.json` — the **Stable** bundles (one folder per stable line).
- `bundles/latest/package.json` — the rolling latest pointer (switching it triggers an image build and an automatic
  `BundleVersion` bump). `bundles/stable.json` maps `"N"` → bundle URL.
- `modules_v3.json` — the **Edge/Alfa** module registry (every module's versions + dependencies), written by each module's
  CI. `modules.json` is the legacy v2.
- `pbc/*.json` — Packaged Business Capability groupings (pin their own platform + module versions).
- `src/` — the **release tooling** (Python). `bundles/RELEASE_PROCEDURE.md` is the canonical how-to.

The actual code lives in **sibling repos** under the monorepo root (`monorepoRoot` in the config):
`vc-platform` + ~117 `vc-module-*`.

## Release model
Three channels: **Alfa** (bleeding edge), **Edge** (`modules_v3.json`), **Stable** (`bundles/vN`).
Cutting a stable = promoting the platform + ~60 modules to a new dependency-ordered release, wave by wave, through PRs.

## Cutting a stable release
Use the **`vc-stable-release` skill** and follow **[bundles/RELEASE_PROCEDURE.md](bundles/RELEASE_PROCEDURE.md)**.
Everything version-specific is in **[src/release.config.json](src/release.config.json)**, read via `src/config.py`;
edit that, not the scripts. Per wave: `python src/prepare_wave.py --wave N`, then `python src/release_wave.py --label wN`.

## Invariants — do not violate
- **Registry edits go on a branch off `master`.** This repo's `dev` is a stale ~14k-commit branch with
  no `bundles/`; never branch from it.
- **PR-gated**: every module change is a PR to `dev`; GitHub Actions is the gate; the repo's `Release` workflow releases
  it. Release only with the user's go-ahead (per wave, or a standing "auto-release green waves").
- **One wave per run** (background jobs are time-limited; an interrupted run can leave watchers that merge or release twice).
- **Obsolete-removal policy**: remove `[Obsolete]` with **no `DiagnosticId`** or a VC id below `obsoleteKeepFrom`
  (Stable 15: keep VC0012+, Stable 16: keep VC0013+). Done in its own ticket before the waves, dependents first.
- **`TreatWarningsAsErrors=true`** in source repos ⇒ obsolete *usage* of a kept member is a build
  error (Stable 16: VC0015 on the synchronous `IIndexingJobService` methods → `…Async`).
- **Wave order = platform first, then topological** (`compute_waves.py`, which also counts csproj-only module references —
  UCP→XOrder was missing from its manifest in Stable 16).
- **Module dependencies go to the latest releases, not just the platform.** Every `VirtoCommerce.*` module
  reference, in the csproj **and** in `module.manifest`, moves to the dependency's latest release. **Pause between waves**
  until nuget.org lists the previous wave's packages. `prepare_wave.py` does both.
- **Surface, don't auto-perform** risky/architectural changes (cascading public-API removals, behavior changes, a red check
  that is not a known flake) — report and let the user decide.

## Tooling (`src/`) — read the docstrings and `src/README.md`
Step 0: `audit_obsolete.py` · `platform_package_reference.py` · `compute_waves.py`.
Waves: `prepare_wave.py` (`bump_platform.py`, `align_3rdparty.py`, `bump_module_deps.py`, `npm_audit_fix.py`,
`gen_pr_body.py`) · `release_wave.py`.
Finalize: `finalize_bundle.py` · `validate_bundle.py` · `collect_releases_md.py` · `collect_breaking_changes.py` ·
`update_pbc.py`. The consumer upgrade script ships per bundle as `bundles/vN/update-to-stable.ps1`; the guide is
`bundles/vN/update_path.md`.

## Environment / gotchas
- Windows + PowerShell 7 + Git Bash. Working files go to the git-ignored `.release-work/v{N}/`.
- Some `src` generators are **not idempotent against live state**: `audit_obsolete.py` and
  `finalize_bundle.py --source local` read the *current* sibling-repo sources. Don't re-run them as a "regression check"
  once work has started. `finalize_bundle.py` defaults to `--source github` (released versions).
- A module's master-CI "Publish Manifest" step can lose a push race on `vc-modules/master`, leaving its stable registry
  entry missing — `validate_bundle.py` catches it.
- Git Bash `sed -i` rewrites CRLF files as LF (whole-file churn): edit byte-level (the src tools do) and check
  `git diff --stat`. Bash `/tmp` ≠ pwsh `/tmp`.
- PowerShell pitfalls: passing a `@{}` hashtable via `pwsh -File` stringifies it — build it inside `-Command` or
  dot-source instead; prefer `Set-Content -Path X -Value Y` over positional binding.
- End-to-end validation suite: [`vc-testing-module`](https://github.com/VirtoCommerce/vc-testing-module)
  (Playwright + pytest); needs `--import-mode=importlib` and exclude `destructive`/`optional`.
