# Virto Commerce Stable bundle: release procedure

This is the single end-to-end procedure for cutting a new **Stable** bundle (`bundles/vN/`). The `vc-stable-release`
Claude skill and the tool docstrings point here. Stable 16 is the worked example: [`v16/`](v16/) holds its deliverables.

> Audience: the release maintainer (a person or Claude Code) working in `vc-modules`, with the source repos
> (`vc-platform`, `vc-module-*`) cloned side by side under the monorepo root.

**The process is PR-gated.** Every module change goes through a PR to `dev`, with GitHub Actions as the quality gate, and is
released by the repo's `Release` workflow. Modules are processed in dependency **waves**. Each wave builds on the modules the
earlier waves released, restoring them from nuget.org. Nothing is built against a local feed.

---

## 0. One config drives the cycle
Everything version- and path-specific lives in **[`src/release.config.json`](../src/release.config.json)**. Edit it once per
release, never the scripts:

| Key | Meaning |
|---|---|
| `version` / `prevVersion` | bundle numbers (`bundles/v{version}`) |
| `platformVersion` / `themeVersion` / `themeUrlTemplate` | the platform and theme the bundle ships |
| `jiraTicket` / `branch` | the cycle's Jira key and the feature branch used in every module repo |
| `obsoleteRemovalTicket` / `obsoleteKeepFrom` | the obsolete-removal ticket; `[Obsolete]` VC ids below `obsoleteKeepFrom` are removed (S15: VC0012, S16: VC0013) |
| `monorepoRoot` | folder holding the `vc-platform` / `vc-module-*` clones |
| `githubOrg` / `sourceBranch` | `VirtoCommerce` / `dev` (PR target; the Release workflow runs on it) |
| `nugetWaitMinutes` | how long a wave waits for the previous wave's packages on nuget.org |
| `flakyChecks` | regex of CI checks that may be re-run once (the auto-tests legs, swagger-validation) |
| `pbcRequiredModules` | modules every `pbc/*.json` grouping must include (S16: `VirtoCommerce.BackgroundJobs`) |

The Python tools read it via `src/config.py`. Working files (PR lists, results, PR bodies, per-repo notes) go to the
git-ignored `.release-work/v{N}/`. Seed `bundles/v{version}/package.json` as a copy of the previous bundle before the first run.

## Core invariants (do not violate)
- **Registry repo (`vc-modules`)**: never branch from its stale `dev`; registry and bundle edits go on a branch off **`master`**.
- **Every module change is a PR to `dev`**, released only after its checks are green. No pushes to `dev`, no local feeds.
- **Obsolete-removal policy**: remove `[Obsolete]` members with **no `DiagnosticId`** or a VC id below `obsoleteKeepFrom`;
  keep the rest. Do it in its own ticket **before** the cycle, dependents first (a consumer must stop using a member before
  the member is removed).
- **`TreatWarningsAsErrors=true`** everywhere: obsolete *usage* of a kept member is a build error. Expect forced migrations
  when a dependency adds a new `[Obsolete]` (Stable 16: VC0015 on the synchronous `IIndexingJobService` methods).
- **Wave order = platform first, then topological** (`compute_waves.py`, which also counts csproj-only module references).
- **Module dependencies go to the latest releases, not just the platform.** Every `VirtoCommerce.*` module reference, both
  csproj `PackageReference` and `module.manifest` `<dependency>`, moves to that module's latest GitHub release. Stale
  references ship old transitive packages: in Stable 16, Catalog 3.1029.0 pulled a vulnerable `AngleSharp` (NU1902).
- **Pause between waves until nuget.org lists the previous wave's packages.** NuGet lags the GitHub release.
  `prepare_wave.py` waits up to `nugetWaitMinutes`.
- **One wave per run.** Background jobs are time-limited. A run that is killed can leave watchers behind that merge or
  release twice. `release_wave.py` guards against both, but don't chain waves.
- **Stop on anything that isn't a known flake or a mechanical fix.** Report it and let the owner decide: cascading API
  removals, behavior changes, a red check outside `flakyChecks`.

---

## 1. Step 0: preparation (read-only review gate)
Make **no code changes** yet. Generate the review artifacts and get sign-off:

| Tool | Output |
|---|---|
| `python src/audit_obsolete.py` | `v{N}/obsolete_removal_audit.md`: every removable obsolete member, with blast radius |
| `python src/platform_package_reference.py` | `v{N}/platform_package_reference.md`: the platform's real third-party versions (the alignment target) |
| `python src/compute_waves.py` | `v{N}/dependency-tree.md`: the waves (no cycles). It also lists **undeclared** csproj-only module dependencies; get those added to the manifests. |

The obsolete removals run as their own ticket (Stable 16: VCST-5901) and are released before the waves start. `audit_obsolete.py`
and `finalize_bundle.py --source local` read the live sources, so they are not idempotent once work has started.

**Platform first.** Release `vc-platform` at `platformVersion` (its own PR and `Release` workflow) before Wave 1.

## 2. The waves
For each wave, in order, run **two commands**, one wave at a time:

```bash
python src/prepare_wave.py --wave 5          # make + verify the changes, open one PR per repo
python src/release_wave.py --label w5        # CI gate -> merge -> Release -> wait for the GitHub release + zip
```

**`prepare_wave.py`**, per repo:
1. Branches off `origin/dev`, or keeps a tree you already prepared on the cycle branch.
2. Platform bump and third-party alignment.
3. Refuses any repo that still uses Hangfire.
4. Bumps module deps to the latest releases, after waiting for nuget.org.
5. Runs `npm audit fix` (never `--force`). If the Web build breaks, it reverts.
6. Clean build (0 warnings) and unit tests.
7. PR body, commit, push, PR.

A repo that fails a step is **not committed**: it's reported as `FAILED (<reason>)` in `.release-work/v{N}/w5-prepare.txt`,
and its working tree keeps the changes. `--dry-run` stops before the commit.

**`release_wave.py`**:
1. Watches every PR's checks. A PR whose only failures match `flakyChecks` gets its failed jobs re-run **once**. Any other
   red check stops the wave, and nothing is merged.
2. When everything is green, per repo: guard (skip a PR that's already merged, or a repo whose Release run is still
   active), squash-merge with `--admin`, one `Release` run on `dev`, then wait for the GitHub release and its `.zip`.

The result is in `w5-release.txt`; its first line is `GREEN-RELEASED` or `STOPPED`.

### When `prepare_wave.py` reports FAILED
Fix the repo by hand on the cycle branch, leave the changes uncommitted, and run that repo again. The kept tree is picked up,
and the PR list for the wave is merged, not overwritten:
```bash
python src/prepare_wave.py --repos vc-module-x-order --label w10
```
Anything the PR body can't know goes in `.release-work/v{N}/notes/<repo>.md`. That text is appended to the Description, and
lines of the form `@@Breaking changes: …` replace that section. Typical cases:

| FAILED reason | Fix |
|---|---|
| `Hangfire migration needed` | Move to the `Platform.Core` job API: payload + `IBackgroundJobHandler<T>`, `AddBackgroundJob` / `AddRecurringJob(...).WithId("<Type>.<Method>").FromSettings(...)`, `IDistributedLock` instead of `[DisableConcurrentExecution]`. Keep the old public target method (or a VC0015 stub) so queued legacy jobs still run. No BackgroundJobs package or manifest dependency; one class per file. See [`v16/update_path.md`](v16/update_path.md). |
| `build: … error VC0015 …` | Apply the `[Obsolete]` recommendation (e.g. `await EnqueueIndexAndDeleteDocumentsAsync(...)`). In Moq, add `It.IsAny<CancellationToken>()` and use `.ReturnsAsync`. Mechanical. |
| `build: … CS1729 / CS0117 …` in tests | A dependency removed an expired obsolete member (e.g. the XCart `CartAggregate` constructor); update the test. |
| `dependency not on nuget.org yet` | The previous wave's packages aren't listed yet; run again later. |
| `dirty working tree` | Local changes on another branch: commit or stash them, or move a stale `nuget.config` aside. |

SonarCloud runs on new code only, so moved job bodies count as new. Watch for more than 7 constructor parameters (S107: use a
thin handler wrapper), nested ternaries (S3358), unread fields (S4487), and blocking `GetResult()` (S4462: `#pragma` with a reason).

### When a released wave turns out stale
If a module was released before its dependencies' latest versions (for example the dependency bump was skipped, or a
csproj-only dependency sat in the same wave), re-run the waves from that point in order. `prepare_wave.py` does only the
missing bumps, and the re-runs cascade because each re-release changes what the next wave must reference. To audit:
```bash
python src/bump_module_deps.py --check --waves 1-12 --ref origin/dev
```

## 3. Finalize the bundle
1. **Final dependency audit**: `python src/bump_module_deps.py --check --waves 1-N --ref origin/dev` must report every repo
   up to date (it ignores `samples/`).
2. **`python src/finalize_bundle.py`**: pins each module's latest GitHub release (with its `.zip`) into `v{N}/package.json`,
   and sets the platform, image tag and theme from the config.
3. **`python src/validate_bundle.py`**: every pinned version needs a stable `modules_v3.json` entry on `master`
   (platform = the bundle's, GitHub-release URL), every required dependency must be in the bundle at or above its floor,
   the platform release must be stable, and the theme URL must resolve.
   - A missing stable entry usually means the module's master-CI "Publish Manifest" step lost a push race on
     `vc-modules/master` (Stable 16: Catalog 3.1048.0). The release is fine; the entry has to be added.
4. **`python src/collect_releases_md.py`**: writes `v{N}/release_notes.md` (prev → current GitHub release notes).
5. **`python src/collect_breaking_changes.py`**: pulls the `## Breaking changes` sections of the cycle's merged PRs
   (`jiraTicket` + `obsoleteRemovalTicket`) into `.release-work/v{N}/breaking_changes_raw.md`. Write `v{N}/breaking_changes.md`
   from it, not from memory.
6. Write `v{N}/update_path.md`, the consumer procedure. Copy the previous `update-to-stable.ps1` and adapt it for the new
   bundle, then **dry-run it on a previous-stable tag** of a module (`git archive <tag> src`) before shipping.
7. Add `"N"` to [`stable.json`](stable.json).
8. **`python src/update_pbc.py --apply`**: brings `pbc/*.json` up to the bundle.
   - Modules outside the bundle move to their newest compatible release. They weren't rebuilt for this platform, so
     include them in the test.
   - `pbcRequiredModules` are added, and each grouping is closed over its dependencies.
9. Commit `bundles/vN/*`, `stable.json` and `pbc/*.json` on a branch off **`master`** and open the bundle PR.

## 4. Verify, then merge
- **End to end on the final solution**: deploy the bundle (platform + `vc-build InstallModules` against `v{N}/package.json`), then
  start the frontend and run the [`vc-testing-module`](https://github.com/VirtoCommerce/vc-testing-module) suite against it:
  `pytest --import-mode=importlib -m "not destructive and not optional"`.
  - Include the PBC groupings.
  - A test that calls a **removed** endpoint must be updated, not treated as a regression.
- After the tests pass, point **`bundles/latest`** at the new bundle. This triggers the image build and the automatic
  `BundleVersion` bump. Then merge the bundle PR.

---

## Known CI behavior
- **Flaky checks** (`flakyChecks`): the frontend Playwright legs (wishlist, ship-to selector, cart configuration, cart merge,
  checkout, sign-in), a GitHub API rate limit in `InstallPlatform`, and a SonarQubeEnd "get the pullrequest" error.
  They are re-run once; a second failure is real.
- **`Release` workflow**: tags the merge commit, attaches the module `.zip`, moves `dev` to the next version, and
  publishes to nuget.org a few minutes later. A second Release run started right after the first fails on `git push`.
  That is harmless, but `release_wave.py` prevents it.
- **Registry publish**: each module's master CI commits its stable entry to `vc-modules/master`. Concurrent alpha publishes
  can make it lose the race (`validate_bundle.py` catches this).

## Deliverables (`bundles/v{N}/`)
`package.json` · `breaking_changes.md` · `release_notes.md` · `update_path.md` · `update-to-stable.ps1` ·
`dependency-tree.md` · `platform_package_reference.md` (· `obsolete_removal_audit.md`). Also the `"N"` entry in
`stable.json` and the `pbc/*.json` update. See [`v16/`](v16/).

## Tooling index (`src/`)
| File | Role |
|---|---|
| `release.config.json` / `config.py` | the per-release config and its loader |
| `audit_obsolete.py` | Step 0: obsolete inventory and blast radius |
| `platform_package_reference.py` | the platform's real NuGet dependencies → md (the alignment target) |
| `compute_waves.py` | dependency tree and waves, including undeclared csproj-only module dependencies |
| `prepare_wave.py` | per wave: bumps, npm audit fix, build/test, PRs (`--dry-run`) |
| `release_wave.py` | per wave: CI gate, guarded merge, Release, wait for release + zip (`--gate-only`) |
| `bump_platform.py` / `align_3rdparty.py` / `bump_module_deps.py` / `npm_audit_fix.py` / `gen_pr_body.py` | the steps `prepare_wave.py` runs; each also works on its own |
| `finalize_bundle.py` | pin released versions into `package.json` (`--source github` default, or `local`) |
| `validate_bundle.py` | bundle vs registry, platform and theme |
| `collect_releases_md.py` | `release_notes.md` from GitHub releases |
| `collect_breaking_changes.py` | Breaking-changes sections of the cycle's merged PRs |
| `update_pbc.py` | `pbc/*.json` to the bundle, closed over dependencies |
