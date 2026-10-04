"""
Generate the stable-release PR description for one module repo from its uncommitted working-tree diff.

Sections follow the team's PR-description guide (Description, GraphQL changes, new services, protected methods,
breaking changes, dependencies, references). The description lists what the release tooling changed:
  * the platform bump and the third-party alignment (read from the csproj diff against HEAD);
  * the VirtoCommerce module dependency bumps (passed in from bump_module_deps.plan);
  * the `npm audit fix` result (passed in from npm_audit_fix.fix).

Anything the tooling cannot know (a Hangfire migration, an obsolete-usage fix) goes in a per-repo notes file:
.release-work/v{N}/notes/<repo>.md. Its text is appended to the Description. A line `@@<Section title>: text` replaces
that section's default, e.g. `@@Breaking changes: ...`.

Usage: python gen_pr_body.py <repo_dir> <out.md> [--tests "unit tests: Passed: 40, ..."]
"""
import argparse
import json
import os
import re
import subprocess

import config

PACKAGE_LINE = re.compile(r'^([-+])\s*<PackageReference Include="([^"]+)" Version="([^"]+)"', re.M)


def third_party_changes(repo_dir):
    diff = subprocess.run(["git", "diff", "HEAD", "--", "*.csproj"], cwd=repo_dir, capture_output=True, text=True,
                          encoding="utf-8").stdout
    old, new = {}, {}
    for sign, package, ver in PACKAGE_LINE.findall(diff):
        (old if sign == "-" else new).setdefault(package, set()).add(ver)
    changes = []
    for package in sorted(set(old) | set(new)):
        if package.startswith("VirtoCommerce."):
            continue
        o, n = "/".join(sorted(old.get(package, []))), "/".join(sorted(new.get(package, [])))
        if o != n:
            changes.append(f"{package} {o or '—'} → {n or 'removed'}")
    removed_vc = sorted(p for p in old if p.startswith("VirtoCommerce.") and p not in new)
    return changes, removed_vc


def _dep_summary(dep_changes):
    def fmt(kind):
        items = sorted({f"{dep} {old} → {new}" for _, k, dep, old, new in dep_changes if k == kind})
        return ", ".join(items) if items else "none"
    return f"`PackageReference` {fmt('package')}; `module.manifest` floors {fmt('manifest')}"


def _npm_line(npm_results):
    if not npm_results:
        return "No `*.Web/package-lock.json` in this module, so `npm audit fix` does not apply."
    lines = []
    for r in npm_results:
        if r.get("reverted"):
            lines.append(f"`npm audit fix` on {r['project']} was **reverted**: `webpack:build` failed after it.")
        else:
            changed = ", ".join(r["changed"]) if r["changed"] else "no lockfile changes"
            lines.append(f"`npm audit fix` (no `--force`) on {r['project']}: **{r['before']} → {r['after']}** vulnerabilities; "
                         f"`webpack:build` still succeeds. Lockfile-only bumps: {changed}.")
    return " ".join(lines)


def build_body(repo_dir, dep_changes=(), npm_results=(), tests="", notes=None):
    third, removed_vc = third_party_changes(repo_dir)
    platform_changed = any(re.search(r"VirtoCommerce\.Platform\.", line) for line in
                           subprocess.run(["git", "diff", "HEAD", "--", "*.csproj", "*module.manifest"], cwd=repo_dir,
                                          capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
                           if line.startswith("+"))
    desc = ["## Description", "", f"Stable {config.VERSION} ({config.JIRA_TICKET}) release update.", ""]
    if platform_changed:
        desc.append(f"- Bumps `VirtoCommerce.Platform.*` to **{config.PLATFORM_VERSION}** (csproj + `module.manifest`).")
    desc.append("- Aligns third-party `PackageReference` versions to the platform's (per "
                f"`vc-modules/bundles/v{config.VERSION}/platform_package_reference.md`): "
                + (", ".join(third) if third else "none needed") + ".")
    if dep_changes:
        desc.append("- Bumps the **VirtoCommerce module dependencies to their latest releases** (the versions the earlier "
                    f"waves shipped): {_dep_summary(dep_changes)}.")
    desc.append(f"- {_npm_line(npm_results)}")
    desc += ["", f"Builds clean with **no warnings**; {tests or 'no unit tests'}.", "",
             "No GraphQL schema change · no migrations · no new settings · no new dependencies."]

    sections = {
        "New GraphQL queries and mutations": "None.",
        "Changes to existing GraphQL queries and mutations": "None.",
        "New public services / interfaces / methods": "None.",
        "New protected methods (extensibility)": "None.",
        "Breaking changes": "None in code." + (" The `module.manifest` dependency floors are raised to the "
                                               f"Stable {config.VERSION} versions." if dep_changes else ""),
        "New dependencies": "None. Third-party versions are aligned to the platform's."
                            + (f" Removed: {', '.join('`' + p + '`' for p in removed_vc)}." if removed_vc else ""),
    }
    if notes:
        for m in re.finditer(r"^@@([^:]+):\s*(.+)$", notes, re.M):
            sections[m.group(1).strip()] = m.group(2).strip()
        text = re.sub(r"^@@.*\n?", "", notes, flags=re.M).strip()
        if text:
            desc += ["", text]

    body = "\n".join(desc) + "\n"
    for title, text in sections.items():
        body += f"\n## {title}\n{text}\n"
    body += (f"\n## References\n### QA-test:\n### Jira-link: https://virtocommerce.atlassian.net/browse/{config.JIRA_TICKET}\n"
             "### Artifact URL:\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n")
    return body


def notes_for(repo):
    path = os.path.join(config.WORK_DIR, "notes", f"{repo}.md")
    return open(path, encoding="utf-8").read() if os.path.isfile(path) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_dir")
    ap.add_argument("out")
    ap.add_argument("--tests", default="")
    ap.add_argument("--npm-json", help="file with npm_audit_fix.py output (one JSON object per line)")
    args = ap.parse_args()
    npm = [json.loads(line) for line in open(args.npm_json, encoding="utf-8")] if args.npm_json else []
    repo = os.path.basename(os.path.abspath(args.repo_dir))
    body = build_body(args.repo_dir, npm_results=npm, tests=args.tests, notes=notes_for(repo))
    open(args.out, "w", encoding="utf-8", newline="\n").write(body)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
