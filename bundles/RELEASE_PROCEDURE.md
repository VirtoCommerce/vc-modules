# Virto Commerce Stable bundle — release procedure

Canonical, end-to-end procedure for cutting a new **Stable** bundle (`bundles/vN/`). This is the
single source of truth for the flow; the `vc-stable-release` Claude skill and the per-tool docstrings
point here. v15 is the worked example — its deliverables in [`v15/`](v15/) are the reference outputs.

> Audience: the release maintainer (human or Claude Code) working in the `vc-modules` repo with the
> sibling source repos (`vc-platform`, `vc-module-*`) checked out under the monorepo root.

---

## 0. One config drives the cycle
Everything version- and path-specific lives in **[`src/release.config.json`](../src/release.config.json)**.
Edit it once per release:

```jsonc
{ "version": 16, "prevVersion": 15,
  "platformVersion": "3.1XXX.0", "themeVersion": "2.XX.0",
  "jiraTicket": "VCST-XXXX", "branch": "feat/VCST-XXXX-stable-16",
  "monorepoRoot": "C:\\Projects\\git\\VirtoCommerce",
  "localNugetPath": "C:\\Projects\\git\\VirtoCommerce\\local-nuget",
  "artifactStagingPath": "C:\\vc-platform-3-demo\\_stable_16_artifacts" }
```

The Python tools read it via `src/config.py`; the PowerShell tools via `src/release-config.ps1`.
No tool has the version/paths hardcoded — change the config, not the scripts. Seed
`bundles/v{version}/package.json` as a copy of the previous bundle before the first run.

## 0.5 Isolated source + runtime sandbox
The release runs **isolated** — it never modifies your day-to-day clones — and is verified at
**runtime** (not just compile) after every wave. Set `sandboxRoot` (+ `healthUrl`) in the config and run:

```powershell
pwsh -File src/setup-sandbox.ps1     # add -Shallow for fast clones, -InstallRuntime to auto-deploy the baseline
```

It creates two trees and repoints the config so all tooling follows automatically:
- **`<sandboxRoot>/src`** — fresh clones of `vc-platform` + every `vc-module-*` (from your current
  `monorepoRoot`). `setup-sandbox.ps1` rewrites `monorepoRoot`/`localNugetPath` in the config to this
  folder (backup `release.config.json.bak`), so `release_module.ps1`, `audit_obsolete.py`,
  `finalize_bundle.py`, etc. all operate on the sandbox. Bundles/registry/deliverables stay in the real
  `vc-modules` repo.
- **`<sandboxRoot>/runtime`** — a platform deployed from the **previous** stable bundle. After install,
  **edit the runtime env file** (DB connection string, etc.) — `setup-sandbox.ps1` prints its path and
  pauses for this.

Then confirm the baseline is healthy before touching code:
```powershell
pwsh -File src/probe-runtime.ps1     # start -> poll /health -> stop ; exit 0 = Healthy
```

## Core invariants (do not violate)
- **Registry repo (`vc-modules`)**: never branch from its stale `dev`; make registry edits on a
  branch off **`master`**.
- **Local-first**: build everything against the `local-nuget` feed; **zero pushes** until the full
  bundle is green locally.
- **Obsolete-removal policy**: remove `[Obsolete]` members with **no `DiagnosticId`** OR
  `DiagnosticId` in **`VC0001`–`VC0011`** (`< VC0012`); **keep `VC0012+`** (active migrations).
- **`TreatWarningsAsErrors=true`** everywhere ⇒ obsolete *usage* of a kept member is a build error
  (forces the `ICancellationToken`/`IModuleCatalog`/etc. migrations).
- **Wave order = platform first, then topological** (a wave compiles against earlier waves' freshly
  packed `local-nuget` outputs).
- **Module dependencies point at the latest releases.** Every `VirtoCommerce.*` module a repo depends on is
  bumped to that module's **latest GitHub release**, which in a running cycle is the version an earlier wave just
  released. This covers both the csproj `PackageReference`s and the `module.manifest` `<dependency>` entries. Bumping
  only the platform is not enough: stale module references ship old transitive packages (Stable 16: Catalog
  3.1029.0 still pulled a vulnerable `AngleSharp` that broke the build with NU1902) and an out-of-date dependency
  floor. Use `src/bump_module_deps.py`.
- **Pause between waves until NuGet has the packages.** A wave restores the previous wave's packages from
  nuget.org, which can list them minutes after the GitHub release. Do not start wave N+1 until every package
  released in wave N is listed (`bump_module_deps.py --apply --wait-nuget 30` blocks until it is).

---

## 1. Step 0 — pre-release audit (READ-ONLY review gate)
Make **no code changes** yet. Generate the review artifacts and get sign-off:

| Tool | Output |
|---|---|
| `python src/audit_obsolete.py` | `v{N}/obsolete_removal_audit.md` — every removable obsolete + risk |
| `python src/platform_package_reference.py` | `v{N}/platform_package_reference.md` — real platform deps |
| `python src/compute_waves.py` | `v{N}/dependency-tree.md` — the waves (validates: no cycles) |

Review `obsolete_removal_audit.md` (what will be removed, blast radius) before proceeding.

## 2. Per-repo flow (platform first, then each module in wave order)
Two git contexts: **source repos** use their real `dev`; the **registry repo** uses `master` (see
invariants). For each source repo, the orchestrator
**[`src/release_module.ps1`](../src/release_module.ps1)** performs:

1. `git checkout dev` → pull → branch `<branch from config>`.
2. Baseline `vc-build Compress` (confirm it builds *before* changes).
3. Write a **local-only `nuget.config`** mapping every `VirtoCommerce.*` already in `local-nuget`
   (platform + earlier waves) to the local feed.
4. Bump **platform** refs (`*.csproj` `PackageReference VirtoCommerce.Platform.*` + `module.manifest
   <platformVersion>`) and **inter-module dependency** versions (csproj + manifest). **Both are required, in
   every flow**, including the CI-driven flow (PR + GitHub Actions instead of `release_module.ps1`):
   ```bash
   python src/bump_module_deps.py --check <repo>                    # what is stale
   python src/bump_module_deps.py --apply <repo> --wait-nuget 30    # bump to the latest releases
   ```
   - The target is each dependency's **latest GitHub release**. Inside a cycle, that is what the earlier wave
     just shipped. The tool bumps upward only, keeps line endings, and leaves anything it can't map to a bundle
     module alone (and reports it).
   - Packages the platform ships besides `VirtoCommerce.Platform.*` (`VirtoCommerce.Testing`) go to `platformVersion`.
   - A wave can only be prepared after the previous wave is **released and on nuget.org**. Run the tool at the
     start of each wave, not ahead of time.
   - To see which already-released repos are stale: `python src/bump_module_deps.py --check --waves 2-8 --ref origin/dev`.
5. **Remove obsolete code** per policy; fix the resulting compile errors *(this step is manual /
   module-specific — the orchestrator does not do removals).* Helpers: `src/migrate_ict.ps1`
   (`ICancellationToken` → `CancellationToken`).
6. `dotnet restore --force` + build against `local-nuget`.
7. `npm audit fix` in each `*.Web` project that has a `package-lock.json`, to bump vulnerable
   dependencies and clear `npm audit` warnings. **Required for every module, in every flow** — the
   CI-driven flow (PR + GitHub Actions instead of `release_module.ps1`) must run it by hand too:
   - Run plain `npm audit fix` only — **never `--force`** (it takes semver-major bumps that can break the
     admin UI). If something stays unfixed without `--force`, leave it and list it in the PR.
   - Run `npm audit` before and after, and put both counts (`N high, M moderate → …`) in the PR description.
   - Commit the updated `package-lock.json` (and `package.json` if it changed). These are the intended
     change, not noise.
   - Verify the Web bundle still builds (`npm run webpack:build`, or `vc-build Compress`). If it breaks,
     revert the lockfile and report it rather than shipping it.
   - Skip, and say so in the PR, when the module has no `*.Web/package-lock.json`.
8. Version bump if needed (obsolete removal is breaking → minor bump).
9. `vc-build Compress` (verify) → `dotnet pack` to `local-nuget` (so later waves consume it) →
   stage the artifact zip to `artifactStagingPath`.

**After each wave, verify at runtime** — deploy the wave's freshly built artifacts into the sandbox
runtime and re-probe health:
```powershell
pwsh -File src/probe-runtime.ps1 -Deploy -Modules <wave module names>   # Wave 0 updates the platform
```
This catches EF-migration / startup breakage that a compile-only check misses. Then **pause and audit**
the diffs + `breaking_changes.md` + build logs + the health result before the next wave. Record every
removal in `v{N}/breaking_changes.md`. **Stop and report any unexpected situation** (a build break that
isn't an obvious obsolete cascade, a runtime probe that goes unhealthy, manifest drift, audit failure).

## 3. Finalize the bundle
- **Final dependency audit first**: `python src/bump_module_deps.py --check --waves 1-N --ref origin/dev`
  must report every repo up to date. It catches modules that shipped against a previous release of a
  same-wave dependency, e.g. a csproj-only module reference that `compute_waves.py` (manifest-based) doesn't see.
  Ignore `samples/*/_module.manifest`, which is never shipped.
- `python src/finalize_bundle.py` — fills `v{N}/package.json` with each module's released version and sets
  `PlatformVersion`/`PlatformImageTag` + the theme URL from the config. The default `--source github` reads each
  repo's latest non-prerelease GitHub release (which must carry the module `.zip`). That is the right source for a CI-driven
  cycle, where local clones sit on other branches or `dev` already carries the next `VersionPrefix`. `--source local`
  reads `Directory.Build.props <VersionPrefix>` (local-first workflow).
- **Validate against the registry**: every pinned version must have a **stable** entry in `master`'s `modules_v3.json`
  (no `VersionTag`, GitHub-release `PackageUrl`, `PlatformVersion` = the bundle's), and every non-optional dependency
  must be in the bundle at or above its floor. A module's master-CI "Publish Manifest" step can lose a push race on
  `vc-modules/master` (Stable 16: Catalog 3.1048.0 conflicted with its own dev alpha publish), which leaves the stable entry
  missing even though the release is fine.
- `python src/collect_releases_md.py` — generates `v{N}/release_notes.md` (prev→current GitHub
  release bodies).
- Add the `"N"` entry to [`stable.json`](stable.json).
- Write `v{N}/update_path.md` (consumer upgrade guide), `v{N}/breaking_changes.md`, and ship `v{N}/update-to-stable.ps1`.
  Build `breaking_changes.md` from the `## Breaking changes` sections of the cycle's merged PRs (search the org for the
  cycle's Jira key, plus the obsolete-removal key) rather than from memory. Dry-run the script on a previous-stable tag of
  a module (`git archive <tag> src`) before shipping it.
- Review `pbc/*.json` (PBC groupings pin their own platform and module versions). They can include modules outside the
  bundle, so decide with the owner instead of bumping them blindly.

## 4. Verify
- **Per repo / per wave**: baseline + post-change `vc-build Compress` both green; each wave compiles
  against earlier waves' `local-nuget` packages.
- **Bundle integrity**: re-run `compute_waves.py` against the final `package.json` (0 cycles; every
  dep satisfied).
- **End-to-end on the final solution**: deploy the full final bundle into the sandbox runtime and leave
  it running, then bring up the frontend and run the suite against the live backend + frontend:
  ```powershell
  pwsh -File src/probe-runtime.ps1 -Deploy -KeepRunning      # boots the final runtime, leaves it up
  # start the frontend (vc-frontend) pointed at the runtime backend, then:
  pytest --import-mode=importlib -m "not destructive and not optional"
  # stop the runtime afterwards (Stop-Process -Id <pid printed by probe-runtime>)
  ```
  Run the [`vc-testing-module`](https://github.com/VirtoCommerce/vc-testing-module) Playwright + pytest
  suite. Known true-positive: any test calling a **removed** endpoint (e.g. `GET /api/stores` in S15)
  must be updated, not treated as a regression.

## 5. Publish (per source repo — only after full local green)
Run this for each ready source repo (platform first, then modules). **Every step is a gate: do not
proceed until the prior GitHub Actions run is green.** (Confirm exact workflow names with
`gh workflow list`.)

1. **Push the feature branch and open a PR into `dev`:**
   ```bash
   git push -u origin <branch>                 # <branch> = the value from release.config.json
   gh pr create --base dev --head <branch> --title "<JIRA>: Stable <N>" --body "..."
   ```
2. **Wait for the PR checks; they must all pass:**
   ```bash
   gh pr checks <pr> --watch                   # blocks until checks finish; non-zero exit if any fail
   ```
   If anything is red, fix on the branch and push again — never merge red.
3. **Merge to `dev`, then wait for the `dev` CI run and confirm it is green:**
   ```bash
   gh pr merge <pr> --merge --delete-branch
   gh run watch $(gh run list --branch dev --limit 1 --json databaseId -q '.[0].databaseId')
   ```
4. **Trigger the `Release` workflow on `dev` and wait for it:**
   ```bash
   gh workflow run "Release" --ref dev
   gh run watch $(gh run list --workflow "Release" --branch dev --limit 1 --json databaseId -q '.[0].databaseId')
   ```
5. **Verify the GitHub release was created:**
   ```bash
   gh release list --limit 5                   # the new version/tag should appear
   gh release view <new-version>               # confirm tag, assets, notes
   ```
   If no release appears, inspect the run (`gh run view --log-failed`) and stop — do not start the
   next repo.
6. **Before the next wave, wait for NuGet.** The release creates the GitHub release first and publishes
   packages to nuget.org after it, sometimes minutes later. The next wave bumps to and restores these versions,
   so it must not start until they are listed. `bump_module_deps.py --apply --wait-nuget 30` waits for them.

After all source repos are released, commit the `vc-modules` deliverables (`bundles/vN/*`, `src/*`,
`stable.json`) on a branch off **`master`** and open its PR.

---

## Deliverables checklist (`bundles/v{N}/`)
`package.json` · `breaking_changes.md` · `release_notes.md` · `obsolete_removal_audit.md` ·
`platform_package_reference.md` · `dependency-tree.md` · `update_path.md` · `update-to-stable.ps1`
— plus the `"N"` entry in `stable.json`. See [`v15/`](v15/) for filled examples.

## Tooling index (`src/`)
| File | Role |
|---|---|
| `release.config.json` | the one per-release config (versions, branch, paths, sandbox, health URL) |
| `config.py` / `release-config.ps1` | config loaders (Python / PowerShell) |
| `setup-sandbox.ps1` | create `<sandboxRoot>/src` (isolated clones) + `<sandboxRoot>/runtime` (previous-stable baseline); repoint config |
| `probe-runtime.ps1` | deploy artifacts → start platform → poll `/health` → stop (per-wave + final E2E gate) |
| `audit_obsolete.py` | Step-0 obsolete inventory + risk |
| `platform_package_reference.py` | real platform NuGet deps → md |
| `compute_waves.py` | dependency tree / waves |
| `bump_module_deps.py` | bump a repo's `VirtoCommerce.*` module deps (csproj + manifest) to their latest releases; `--check` audits, `--wait-nuget` gates on nuget.org |
| `finalize_bundle.py` | fill `package.json` from released versions (`--source github` default, or `local`) |
| `collect_releases_md.py` | `release_notes.md` from GitHub releases (supersedes the legacy `collect_releases.py`/`modules_config.json` HTML generator) |
| `release_module.ps1` | per-module orchestrator (branch/bump/build/audit/compress/pack/stage) |
| `migrate_ict.ps1` | `ICancellationToken` → `CancellationToken` helper |
