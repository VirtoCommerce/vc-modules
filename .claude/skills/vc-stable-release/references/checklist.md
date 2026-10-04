# Stable release: per-cycle checklist

Copy this into the release ticket or PR and tick items off as you go. `N` is the new stable number.

## Setup
- [ ] Edit `src/release.config.json`: `version=N`, `prevVersion=N-1`, `platformVersion`, `themeVersion`, `jiraTicket`,
      `branch`, `obsoleteRemovalTicket`, `obsoleteKeepFrom`, `pbcRequiredModules`.
- [ ] Seed `bundles/vN/package.json` from `bundles/v{N-1}/package.json`.
- [ ] Clone or fetch `vc-platform` and every `vc-module-*` under `monorepoRoot`. Move aside any stale `nuget.config` that maps
      `VirtoCommerce.*` to a local feed.
- [ ] `gh` is authenticated with bypass-merge permission on the module repos.

## Step 0 (no code changes; review gate)
- [ ] `python src/audit_obsolete.py` → review `vN/obsolete_removal_audit.md`.
- [ ] `python src/platform_package_reference.py` → `vN/platform_package_reference.md`.
- [ ] `python src/compute_waves.py` → `vN/dependency-tree.md`: 0 cycles; undeclared csproj-only dependencies are fixed or accepted.
- [ ] **User sign-off.**
- [ ] Obsolete removal (its own ticket) is released, dependents first.
- [ ] `vc-platform` is released at `platformVersion`.

## Each wave (one at a time, separate runs)
- [ ] `python src/prepare_wave.py --wave W`. It waits for the previous wave's packages on nuget.org.
- [ ] Every `FAILED` repo is fixed by hand (Hangfire migration, VC0015 fix, test update), explained in
      `.release-work/vN/notes/<repo>.md`, and re-run with `--repos <repo> --label wW`. Non-mechanical choices went to the user.
- [ ] PR descriptions reviewed if the user asked to see them.
- [ ] `python src/release_wave.py --label wW` → `GREEN-RELEASED`. On `STOPPED`, read `wW-release.txt` and report.

## Finalize
- [ ] `python src/bump_module_deps.py --check --waves 1-N --ref origin/dev` reports every repo up to date.
- [ ] `python src/finalize_bundle.py` → `vN/package.json`.
- [ ] `python src/validate_bundle.py` reports no problems (fix any missing registry entry on `master`).
- [ ] `python src/collect_releases_md.py` → `vN/release_notes.md`.
- [ ] `python src/collect_breaking_changes.py`, then write `vN/breaking_changes.md` from it.
- [ ] Write `vN/update_path.md`. Adapt `vN/update-to-stable.ps1` and dry-run it on a previous-stable tag.
- [ ] Add `"N"` to `bundles/stable.json`.
- [ ] `python src/update_pbc.py --apply` (review the not-in-bundle modules it reports).
- [ ] Bundle PR off `master`: `bundles/vN/*`, `stable.json`, `pbc/*.json`.

## Verify, then merge
- [ ] Deploy the bundle; run `vc-testing-module` (`pytest --import-mode=importlib -m "not destructive and not optional"`),
      PBC groupings included. A test hitting a removed endpoint is a true positive: update the test.
- [ ] Point `bundles/latest` at the new bundle (when the user says so), then merge the bundle PR.
