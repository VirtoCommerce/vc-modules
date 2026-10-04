---
name: vc-stable-release
description: >-
  Use when cutting or updating a Virto Commerce Stable bundle release in the vc-modules repo —
  promoting the platform + modules to a new stable line (bundles/vN/), computing dependency-ordered
  update waves, preparing and releasing module waves through PRs and GitHub Actions, bumping
  platform/module versions across csproj + module.manifest, migrating modules for platform changes,
  or producing the release deliverables (package.json, breaking_changes, release_notes, update_path,
  update-to-stable.ps1, stable.json, PBC groupings). Triggers on phrases like "cut stable 17",
  "next stable release", "run wave 5", "release the wave", "update the bundle to platform 3.1xxx",
  "compute the release waves".
---

# Cutting a Virto Commerce Stable release

The full procedure is **[bundles/RELEASE_PROCEDURE.md](../../../bundles/RELEASE_PROCEDURE.md)**, and the repo rules are in
**[CLAUDE.md](../../../CLAUDE.md)**. Read both. This skill is the operational entry point.

## Golden rules (check them before acting)
- Registry and bundle edits go on a branch off **`master`**, never the stale `dev`.
- **PR-gated**: every module change is a PR to `dev`; GitHub Actions is the gate; the repo's `Release` workflow releases it.
  **Release only with the user's go-ahead** for that wave, or under a standing instruction such as "auto-release each green wave".
- **One wave per run.** Run `prepare_wave.py`, then `release_wave.py`, as separate background jobs. Never chain waves: a killed
  job leaves watchers behind that can merge or release twice.
- **Bump module dependencies, not only the platform.** Every `VirtoCommerce.*` module reference (csproj and `module.manifest`)
  goes to the latest release. **Pause between waves** until nuget.org lists the previous wave's packages.
  `prepare_wave.py` does both.
- Obsolete removal is its own ticket before the waves. The policy: remove no-`DiagnosticId` members and VC ids below
  `obsoleteKeepFrom`. `TreatWarningsAsErrors` turns obsolete *usage* into build errors, so apply the `[Obsolete]`
  recommendation mechanically.
- **Stop and report** anything that isn't a known flake (`flakyChecks`) or a mechanical fix: API or behavior decisions, a
  real red check, a cascading removal. Surface it; don't auto-perform it.

## One config drives the cycle
Edit **[src/release.config.json](../../../src/release.config.json)** (version, prevVersion, platformVersion, themeVersion,
jiraTicket, branch, obsoleteRemovalTicket/obsoleteKeepFrom, flakyChecks, pbcRequiredModules). Never hard-code versions in the
scripts. Seed `bundles/v{version}/package.json` from the previous bundle first.

## Steps (details in RELEASE_PROCEDURE.md)
1. **Step 0 (review gate, no edits)**: run `audit_obsolete.py`, `platform_package_reference.py` and `compute_waves.py`.
   Get sign-off, and have undeclared csproj-only module dependencies (listed by `compute_waves.py`) added to the manifests.
   Release `vc-platform` first.
2. **Waves**, one at a time:
   ```bash
   python src/prepare_wave.py --wave N          # branch, bumps, npm audit fix, build+tests, PRs
   python src/release_wave.py --label wN        # CI gate (1 flake re-run), guarded merge, Release, wait for release + zip
   ```
   - On `FAILED`, fix the repo by hand on the cycle branch: a Hangfire → job API migration, a VC0015 obsolete fix, a test
     broken by a removed member. Explain it in `.release-work/v{N}/notes/<repo>.md`, then run
     `prepare_wave.py --repos <repo> --label wN` again.
   - Non-mechanical choices go to the user, for example a legacy job stub, or a new setting replacing an evaluator.
3. **Finalize**:
   - `bump_module_deps.py --check --waves 1-N --ref origin/dev` must report every repo up to date.
   - Run `finalize_bundle.py`, then `validate_bundle.py`, then `collect_releases_md.py` and `collect_breaking_changes.py`.
   - Write `breaking_changes.md` and `update_path.md`.
   - Adapt `update-to-stable.ps1` and dry-run it on a previous-stable tag.
   - Add `"N"` to `stable.json`, then run `update_pbc.py --apply`.
   - Open the bundle PR off `master`.
4. **Verify**: deploy the bundle and run the `vc-testing-module` suite, including the PBC groupings. Only then point `bundles/latest`
   at the new bundle and merge (the user decides when).

## Reference
- Per-release checklist: [references/checklist.md](references/checklist.md)
- Worked example: `bundles/v16/` (the Stable 16 deliverables).
