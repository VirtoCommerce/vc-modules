# src — Stable-release tooling

Scripts that drive a Virto Commerce **Stable bundle** release. The end-to-end procedure is in
[`bundles/RELEASE_PROCEDURE.md`](../bundles/RELEASE_PROCEDURE.md); repo rules are in [`CLAUDE.md`](../CLAUDE.md);
the guided workflow is the `vc-stable-release` Claude skill.

## To cut the next stable
1. Edit **`release.config.json`** (`version`, `prevVersion`, `platformVersion`, `themeVersion`,
   `jiraTicket`, `branch`, paths). **This is the only file you change per release** — the tools read it.
2. Seed `bundles/v{version}/package.json` from the previous bundle.
3. Follow `bundles/RELEASE_PROCEDURE.md` (Step 0 audit → waves → finalize → verify).

## Config
| File | Role |
|---|---|
| `release.config.json` | single per-release config (versions, branch, local paths) |
| `config.py` | Python loader — exposes `CUR_BUNDLE`, `PREV_BUNDLE`, `REGISTRY`, `PLATFORM_VERSION`, `THEME_URL`, `out(name)`, … |
| `release-config.ps1` | PowerShell loader — `Get-ReleaseConfig` returns versions + resolved paths |

## Tools
| Script | Purpose | Output |
|---|---|---|
| `audit_obsolete.py` | Step-0 obsolete inventory + blast-radius risk (read-only) | `v{N}/obsolete_removal_audit.md` |
| `platform_package_reference.py` | real platform NuGet deps from `VirtoCommerce.Platform.sln` | `v{N}/platform_package_reference.md` |
| `compute_waves.py` | dependency tree / update waves (Kahn topo-sort; cycle check) | `v{N}/dependency-tree.md` |
| `finalize_bundle.py` | fill `package.json` from each repo's released `VersionPrefix` + platform/theme from config | `v{N}/package.json` |
| `collect_releases_md.py` | aggregate GitHub release notes prev→current (uses `gh auth token`) | `v{N}/release_notes.md` |
| `release_module.ps1` | per-module orchestrator: branch, local nuget.config, bump platform/deps, build, `npm audit fix`, `vc-build Compress`, pack→local-nuget, stage artifact | built/packed module |
| `migrate_ict.ps1` | `ICancellationToken` → `System.Threading.CancellationToken` helper | edited `*.cs` |

Consumer-facing upgrade script ships per bundle as `bundles/v{N}/update-to-stable.ps1` (+ `update_path.md`).

## Caveats
- `audit_obsolete.py` and `finalize_bundle.py` read the **live** sibling-repo sources, so they are
  **not idempotent** once the release's removals/bumps are applied — run them at Step 0 / finalize, not
  as mid-release regression checks.
- Requires Python 3 with `requests` + `packaging`; PowerShell 7; `gh` authenticated (for release notes);
  the `vc-build` global tool; and the sibling repos + `local-nuget` under `monorepoRoot`.

## Legacy
`collect_releases.py` + `modules_config.json` are the **superseded** HTML release-notes generator
(manual version map). Use `collect_releases_md.py` instead (Markdown, versions derived from the bundles).
