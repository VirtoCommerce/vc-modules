# Stable release — per-cycle checklist

Copy this into the release tracking issue/PR and tick as you go. `N` = new stable number.

## Setup
- [ ] Edit `src/release.config.json`: `version=N`, `prevVersion=N-1`, `platformVersion`,
      `themeVersion`, `jiraTicket`, `branch`, paths, `sandboxRoot`, `healthUrl`.
- [ ] Seed `bundles/vN/package.json` from `bundles/v{N-1}/package.json`.
- [ ] Confirm sibling repos (`vc-platform`, `vc-module-*`) + `local-nuget` exist under `monorepoRoot`.

## Isolate (sandbox + runtime baseline)
- [ ] `pwsh src/setup-sandbox.ps1` → clones into `<sandboxRoot>/src`, repoints config, deploys prev stable to `<sandboxRoot>/runtime`.
- [ ] **Edit the runtime env file** (DB connection, etc.) — path printed by setup-sandbox.
- [ ] `pwsh src/probe-runtime.ps1` → baseline is **Healthy** before any edit.

## Step 0 — audit (no code changes; review gate)
- [ ] `python src/audit_obsolete.py` → review `vN/obsolete_removal_audit.md`.
- [ ] `python src/platform_package_reference.py` → `vN/platform_package_reference.md`.
- [ ] `python src/compute_waves.py` → `vN/dependency-tree.md` (0 cycles).
- [ ] **User sign-off on the audit before any edit.**

## Obsolete-removal policy (apply per repo)
- Remove `[Obsolete]` with **no `DiagnosticId`** OR `DiagnosticId` **`VC0001`–`VC0011`**.
- **Keep `VC0012+`**. Removing a kept member's *usage* is still required (TreatWarningsAsErrors).
- Defer cascading public-API/interface removals that break downstream + tests; record as deferred.

## Waves (platform first, then topological; pause + audit after each)
- [ ] Wave 0: `vc-platform` → clean obsolete, build, pack to `local-nuget`.
- [ ] Each module: `pwsh src/release_module.ps1 -Repo <repo>` (+ `migrate_ict.ps1` if it uses
      `ICancellationToken`). Build green against `local-nuget`; npm audit; Compress; pack; stage artifact.
- [ ] Each module (any flow, incl. CI-driven PRs): bump **module dependencies**, not just the platform.
      `python src/bump_module_deps.py --apply <repo> --wait-nuget 30` moves every `VirtoCommerce.*` module
      PackageReference **and** `module.manifest` `<dependency>` to its latest release. `VirtoCommerce.Testing` goes
      to `platformVersion`. Run it at the start of the wave, after the previous wave is released.
- [ ] **Between waves:** wait until every package the previous wave released is listed on nuget.org before
      starting the next one. `--wait-nuget` polls for it.
- [ ] Each module (any flow, incl. CI-driven PRs): `npm audit fix` (never `--force`) in every
      `*.Web` with a `package-lock.json`; commit the lockfile; Web bundle still builds; before→after
      `npm audit` counts + anything left unfixed go in the PR. See RELEASE_PROCEDURE.md §2 step 7.
- [ ] **After each wave**: `pwsh src/probe-runtime.ps1 -Deploy -Modules <wave>` → runtime **Healthy**.
- [ ] Every removal recorded in `vN/breaking_changes.md` with replacement guidance.

## Finalize
- [ ] `python src/finalize_bundle.py` → `vN/package.json` (platform/theme from config).
- [ ] `python src/collect_releases_md.py` → `vN/release_notes.md`.
- [ ] Add `"N"` entry to `bundles/stable.json`.
- [ ] Write `vN/update_path.md`; ship `vN/update-to-stable.ps1`.

## Verify (final E2E on the running solution)
- [ ] Re-run `compute_waves.py` on final `package.json` — 0 cycles, deps satisfied.
- [ ] `pwsh src/probe-runtime.ps1 -Deploy -KeepRunning` → full final bundle boots Healthy, left running.
- [ ] Bring up the frontend pointed at the runtime backend.
- [ ] `vc-testing-module`: `pytest --import-mode=importlib -m "not destructive and not optional"`.
      (Update any test that hits a removed endpoint; that's a true positive, not a regression.)
- [ ] Stop the runtime.

## Publish (per source repo — only after full local green; every step is a green gate)
- [ ] Push the feature branch; `gh pr create --base dev`.
- [ ] `gh pr checks <pr> --watch` — all checks pass (fix + repush if red; never merge red).
- [ ] `gh pr merge <pr> --merge` to `dev`; `gh run watch` the `dev` CI — green.
- [ ] `gh workflow run "Release" --ref dev`; `gh run watch` it — green.
- [ ] `gh release view <new-version>` — confirm the release was created (else `gh run view --log-failed`, stop).
- [ ] After all repos released: commit `vc-modules` deliverables (`bundles/vN/*`, `src/*`, `stable.json`) on a branch off `master`.
