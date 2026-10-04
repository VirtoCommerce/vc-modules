# src: Stable-release tooling

These scripts drive a Virto Commerce **Stable bundle** release. The end-to-end procedure is in
[`bundles/RELEASE_PROCEDURE.md`](../bundles/RELEASE_PROCEDURE.md), the repo rules are in [`CLAUDE.md`](../CLAUDE.md), and the
guided workflow is the `vc-stable-release` Claude skill.

## To cut the next stable
1. Edit **`release.config.json`**. It is the only file you change per release; every tool reads it.
2. Seed `bundles/v{version}/package.json` from the previous bundle.
3. Follow `bundles/RELEASE_PROCEDURE.md`: Step 0 → platform → waves (`prepare_wave.py` + `release_wave.py`, one wave per
   run) → finalize → verify.

## Config
| File | Role |
|---|---|
| `release.config.json` | the per-release config: versions, branch, Jira keys, obsolete policy, flaky checks, PBC required modules |
| `config.py` | the loader: `CUR_BUNDLE`, `PREV_BUNDLE`, `REGISTRY`, `PLATFORM_VERSION`, `THEME_URL`, `out(name)` (deliverables), `work(name)` (`.release-work/v{N}/`, git-ignored), … |

## Tools
| Script | Purpose | Output |
|---|---|---|
| `audit_obsolete.py` | Step 0: obsolete inventory and blast-radius risk (read-only) | `v{N}/obsolete_removal_audit.md` |
| `platform_package_reference.py` | the platform's real NuGet dependencies, from `VirtoCommerce.Platform.sln` | `v{N}/platform_package_reference.md` |
| `compute_waves.py` | dependency tree and waves (manifest dependencies plus csproj-only module references; cycle check) | `v{N}/dependency-tree.md` |
| `prepare_wave.py` | per wave: branch, platform bump, alignment, module deps (waits for nuget.org), npm audit fix, build/test, PRs | PRs, `.release-work/v{N}/w{W}-prepare.txt`, `-prs.txt` |
| `release_wave.py` | per wave: CI gate (one flake re-run), guarded merge, `Release` run, wait for GitHub release + zip | releases, `w{W}-release.txt` |
| `bump_platform.py` | `VirtoCommerce.Platform.*` + `<platformVersion>` + FluentAssertions range (never `Platform.Hangfire`) | edited csproj/manifest |
| `align_3rdparty.py` | third-party versions → the platform's | edited csproj |
| `bump_module_deps.py` | `VirtoCommerce.*` module references (csproj + manifest) → latest releases; `--check` audits | edited csproj/manifest |
| `npm_audit_fix.py` | `npm audit fix` (never `--force`) + `webpack:build`, reverting on failure | JSON per Web project |
| `gen_pr_body.py` | PR description from the working-tree diff + `notes/<repo>.md` | markdown |
| `finalize_bundle.py` | pin released versions (`--source github` default, or `local`) + platform/theme | `v{N}/package.json` |
| `validate_bundle.py` | bundle vs `modules_v3.json` on master, platform release, theme URL | report |
| `collect_releases_md.py` | GitHub release notes, prev → current (uses `gh auth token`) | `v{N}/release_notes.md` |
| `collect_breaking_changes.py` | the `## Breaking changes` sections of the cycle's merged PRs | `.release-work/v{N}/breaking_changes_raw.md` |
| `update_pbc.py` | `pbc/*.json` → the bundle; required modules added; closed over dependencies | edited `pbc/*.json` |

The consumer-facing upgrade script ships per bundle as `bundles/v{N}/update-to-stable.ps1` (with `update_path.md`).

## Caveats
- `audit_obsolete.py` and `finalize_bundle.py --source local` read the **live** source repos, so they are not idempotent
  once the release's changes are applied. Run them at Step 0 and at finalize, not as mid-release checks.
- Requirements: Python 3 with `requests` and `packaging`; .NET SDK; Node/npm; `gh`, authenticated, with bypass-merge permission
  on the module repos; the `vc-platform` / `vc-module-*` clones under `monorepoRoot`.
- `prepare_wave.py` changes the module clones: it checks out the cycle branch off `origin/dev`. Commit or stash local work first.
