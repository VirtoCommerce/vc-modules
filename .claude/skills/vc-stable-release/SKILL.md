---
name: vc-stable-release
description: >-
  Use when cutting or updating a Virto Commerce Stable bundle release in the vc-modules repo —
  promoting the platform + modules to a new stable line (bundles/vN/), computing dependency-ordered
  update waves, removing obsolete code per the VC0012 policy, bumping platform/module versions across
  csproj + module.manifest, or producing the release deliverables (breaking_changes, release_notes,
  obsolete_removal_audit, dependency-tree, update_path). Triggers on phrases like "cut stable 16",
  "next stable release", "update the bundle to platform 3.1xxx", "compute the release waves".
---

# Cutting a Virto Commerce Stable release

The full, authoritative procedure is **[bundles/RELEASE_PROCEDURE.md](../../../bundles/RELEASE_PROCEDURE.md)**
and the repo rules are in **[CLAUDE.md](../../../CLAUDE.md)**. Read those. This skill is the operational
entry point.

## Golden rules (verify you're honoring these before acting)
- Registry edits branch off **`master`**, never the stale `dev`.
- **Local-first**: build against `local-nuget`, zero pushes until the whole bundle is green.
- Obsolete-removal: remove **no-DiagnosticId or `VC0001`–`VC0011`**; keep **`VC0012+`**.
- `TreatWarningsAsErrors` makes obsolete *usage* of kept members a build error → expect forced migrations.
- **Surface** risky/cascading public-API changes; don't auto-perform them.
- **Bump module dependencies too, not only the platform.** Every `VirtoCommerce.*` module reference, in both the
  csproj and `module.manifest`, goes to the dependency's latest release, which is what earlier waves just shipped.
  Use `python src/bump_module_deps.py --apply <repo> --wait-nuget 30`. Skipping this in Stable 16 left 39 released
  modules on stale references, and their waves had to be re-run.
- **Pause between waves** until nuget.org lists the previous wave's packages, because publishing lags the GitHub
  release. `--wait-nuget` enforces it.

## One config drives the cycle
Edit **[src/release.config.json](../../../src/release.config.json)** (version,
prevVersion, platformVersion, themeVersion, jiraTicket, branch, paths). All tools read it — never
hardcode versions/paths in the scripts. Seed `bundles/v{version}/package.json` from the previous bundle first.

## Isolation & runtime sandbox
The release runs **isolated** (never touches your day-to-day clones) and verifies at **runtime**, not
just compile. `setup-sandbox.ps1` builds `<sandboxRoot>/src` (fresh clones the release edits —
`monorepoRoot`/`localNugetPath` are repointed there automatically, so every tool follows) and
`<sandboxRoot>/runtime` (a platform deployed from the PREVIOUS stable). `probe-runtime.ps1` boots the
runtime, polls `/health`, and stops it — run it as a **gate after every wave**.

## Steps (each names the tool to run; details in RELEASE_PROCEDURE.md)
1. **Isolate** — `pwsh src/setup-sandbox.ps1`: clones into `<sandboxRoot>/src`, repoints the config,
   deploys the previous stable into `<sandboxRoot>/runtime`. **Pause and ask the user to edit the
   runtime env file** (DB connection string, etc.). Then baseline-probe `pwsh src/probe-runtime.ps1`
   (start → `/health` Healthy → stop). Do not proceed until the baseline is healthy.
2. **Step 0 audit (review gate, no edits)** — `python src/audit_obsolete.py`,
   `platform_package_reference.py`, `compute_waves.py`. Get sign-off on `obsolete_removal_audit.md`.
3. **Waves (platform first, then topological)** — per repo, `pwsh src/release_module.ps1 -Repo <repo>`
   (branch → local nuget.config → bump platform/deps → remove obsolete → build → npm audit → Compress
   → pack → stage). The module-dependency bump is `python src/bump_module_deps.py --apply <repo> --wait-nuget 30`;
   run it in the CI-driven flow as well, at the start of each wave. `migrate_ict.ps1` for the `ICancellationToken` migration. **After each wave, deploy
   + re-probe the runtime**: `pwsh src/probe-runtime.ps1 -Deploy -Modules <wave modules>` (Wave 0 updates
   the platform in the runtime). **Pause and audit after each wave** (build + health + diffs); record
   removals in `breaking_changes.md`.
4. **Finalize** — `finalize_bundle.py`, `collect_releases_md.py`, add `"N"` to `stable.json`, write
   `update_path.md` + ship `update-to-stable.ps1`.
5. **Verify (final E2E on the running solution)** — re-run `compute_waves.py` (0 cycles); deploy the
   full final bundle and leave the runtime up (`pwsh src/probe-runtime.ps1 -Deploy -KeepRunning`), bring
   up the frontend, then run the `vc-testing-module` suite against the running backend + frontend
   (`pytest --import-mode=importlib -m "not destructive and not optional"`). Stop the runtime after.
6. **Publish** (per repo, only after full local green) — push branch → PR to `dev` → `gh pr checks
   --watch` (green) → merge to `dev` → watch `dev` CI (green) → `gh workflow run "Release" --ref dev`
   → watch it → confirm a GitHub release exists (`gh release view`) → **wait until its packages are on
   nuget.org before starting the next wave**. Each step is a gate; never proceed on red. Then commit the `vc-modules` deliverables on a branch off `master`. Full commands in
   RELEASE_PROCEDURE.md §5.

## Reference
- Per-release checklist: [references/checklist.md](references/checklist.md)
- Worked example outputs: `bundles/v15/` (the deliverables from Stable 15).
