"""
Prepare one stable-release wave: per module repo, make the release changes, prove them locally, open a PR.

Per repo:
  1. Branch: `release.config.json` branch off `origin/<sourceBranch>`. A repo already on that branch with uncommitted
     changes is KEPT as is (prepared by hand, e.g. a Hangfire migration or an obsolete fix); any other dirty tree fails.
     A stale Stable-15 `nuget.config` that maps VirtoCommerce.* to a local feed is moved aside.
  2. Platform bump + third-party alignment (bump_platform.py, align_3rdparty.py).
  3. Refuse a repo that still references `VirtoCommerce.Platform.Hangfire` / Hangfire: it needs a code migration first.
  4. Module dependencies -> latest releases (bump_module_deps.py), waiting for nuget.org (`nugetWaitMinutes`), since
     NuGet publishing lags the previous wave's GitHub releases.
  5. `npm audit fix` on the Web project (npm_audit_fix.py).
  6. `dotnet build --no-incremental` (must be 0 warnings / 0 errors) and unit tests (`Category!=IntegrationTest`; when
     every test is integration-tagged, all of them).
  7. PR body (gen_pr_body.py, plus .release-work/v{N}/notes/<repo>.md), commit, push, PR to `sourceBranch`.

A repo that fails any step is NOT committed and is reported as FAILED with the reason; fix it by hand (the working
tree keeps the changes) and run this again for that repo only: the kept tree is picked up.
Nothing is merged or released here; that is release_wave.py.

Results: .release-work/v{N}/<label>-prepare.txt (one line per repo) and <label>-prs.txt ("<repo> <pr url>").

Usage:
  python prepare_wave.py --wave 9                          # every repo of wave 9 (bundles/v{N}/dependency-tree.md)
  python prepare_wave.py --repos vc-module-x-order --label w10b
  python prepare_wave.py --repos vc-module-x-frontend --dry-run       # no commit / push / PR
"""
import argparse
import glob
import os
import re
import subprocess

import align_3rdparty
import bump_module_deps
import bump_platform
import config
import gen_pr_body
import npm_audit_fix

HANGFIRE = re.compile(rb'Include="(VirtoCommerce\.Platform\.Hangfire|Hangfire[.A-Za-z]*)"|^using Hangfire', re.M)
TEST_SUMMARY = re.compile(r"(Passed|Failed)! +- Failed: +(\d+), Passed: +(\d+), Skipped: +(\d+), Total: +(\d+)")


def run(args, cwd, check=False):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=check)


def git(repo_dir, *args):
    return run(["git", *args], repo_dir)


class Failed(Exception):
    pass


def prepare_branch(repo_dir):
    for cfg in glob.glob(os.path.join(repo_dir, "[Nn]u[Gg]et.[Cc]onfig")):
        if "local-" in open(cfg, encoding="utf-8", errors="replace").read():
            os.replace(cfg, cfg + ".stablebak")
    dirty = [l for l in git(repo_dir, "status", "--porcelain").stdout.splitlines() if not l.startswith("??")]
    current = git(repo_dir, "branch", "--show-current").stdout.strip()
    git(repo_dir, "fetch", "-q", "origin", config.SOURCE_BRANCH)
    if dirty and current == config.BRANCH:
        return "kept the prepared working tree"
    if dirty:
        raise Failed(f"dirty working tree on {current}")
    if git(repo_dir, "checkout", "-q", "-B", config.BRANCH, f"origin/{config.SOURCE_BRANCH}").returncode:
        raise Failed("branch")
    return f"fresh from origin/{config.SOURCE_BRANCH}"


def hangfire_refs(repo_dir):
    hits = []
    for pattern in ("**/*.csproj", "**/*.cs"):
        for path in glob.glob(os.path.join(repo_dir, pattern), recursive=True):
            if bump_platform.SKIP.search(path):
                continue
            if HANGFIRE.search(open(path, "rb").read()):
                hits.append(os.path.relpath(path, repo_dir))
    return hits


def build_and_test(repo_dir):
    sln = sorted(glob.glob(os.path.join(repo_dir, "*.sln")) + glob.glob(os.path.join(repo_dir, "*.slnx")))
    if not sln:
        raise Failed("no solution file")
    build = run(["dotnet", "build", sln[0], "-c", "Debug", "--nologo", "--no-incremental"], repo_dir)
    warnings = re.search(r"(\d+) Warning\(s\)", build.stdout)
    errors = re.search(r"(\d+) Error\(s\)", build.stdout)
    problems = sorted({re.sub(r" \[[^\]]*\]$", "", l.strip()) for l in build.stdout.splitlines()
                       if " error " in l or " warning " in l})
    if not errors or errors.group(1) != "0":
        raise Failed("build: " + " | ".join(problems[:8]))
    if not warnings or warnings.group(1) != "0":
        raise Failed("warnings: " + " | ".join(problems[:8]))
    test = run(["dotnet", "test", sln[0], "-c", "Debug", "--nologo", "--no-build",
                "--filter", "Category!=IntegrationTest"], repo_dir)
    found = TEST_SUMMARY.findall(test.stdout)
    if not found:   # every test is IntegrationTest-tagged: run them all and say so
        test = run(["dotnet", "test", sln[0], "-c", "Debug", "--nologo", "--no-build"], repo_dir)
        found = TEST_SUMMARY.findall(test.stdout)
    if any(r[0] == "Failed" for r in found):
        raise Failed("tests: " + "; ".join(f"Failed: {r[1]}, Passed: {r[2]}" for r in found))
    summary = "; ".join(f"Passed: {r[2]}, Skipped: {r[3]}, Total: {r[4]}" for r in found)
    return f"unit tests: {summary}" if summary else "no unit tests"


def prepare(repo, dry_run=False):
    repo_dir = os.path.join(config.MONOREPO_ROOT, repo)
    if not os.path.isdir(repo_dir):
        raise Failed("no such repo")
    branch_note = prepare_branch(repo_dir)

    bump_platform.bump(repo_dir)
    align_3rdparty.align(repo_dir, apply=True)
    hits = hangfire_refs(repo_dir)
    if hits:
        raise Failed("Hangfire migration needed: " + ", ".join(hits[:6]))

    dep_changes, notes = bump_module_deps.plan(repo)
    lagging = [n for n in notes if "not on nuget.org" in n]
    if lagging:
        raise Failed("dependency not on nuget.org yet: " + "; ".join(lagging))
    bump_module_deps.apply(repo, dep_changes)

    if not [l for l in git(repo_dir, "status", "--porcelain").stdout.splitlines() if not l.startswith("??")]:
        return None, "nothing to change (already current)"

    npm = npm_audit_fix.fix(repo_dir)
    tests = build_and_test(repo_dir)

    body_path = config.work(f"pr/{repo}.md")
    with open(body_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(gen_pr_body.build_body(repo_dir, dep_changes, npm, tests, gen_pr_body.notes_for(repo)))
    if dry_run:
        return None, f"DRY RUN: ready to commit ({branch_note} | {tests}); PR body {body_path}"
    for junk in ("nul",):
        if os.path.exists(os.path.join(repo_dir, junk)):
            os.remove(os.path.join(repo_dir, junk))
    git(repo_dir, "add", "-A", "--", ".", ":!.serena", ":!docs/plans", ":!docs/specs", ":!*.stablebak")
    title = f"{config.JIRA_TICKET}: Stable {config.VERSION} release update"
    message = (f"{title}\n\nPlatform {config.PLATFORM_VERSION}, third-party alignment, VirtoCommerce module dependencies "
               "at their latest releases, npm audit fix.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
    if git(repo_dir, "commit", "-q", "-m", message).returncode:
        raise Failed("commit")
    push = git(repo_dir, "push", "-q", "-u", "origin", config.BRANCH)
    if push.returncode:
        raise Failed("push: " + push.stderr.strip()[:200])
    pr = run(["gh", "pr", "create", "--base", config.SOURCE_BRANCH, "--head", config.BRANCH, "--title", title,
              "--body-file", body_path], repo_dir)
    url = re.search(r"https://github\.com/\S+/pull/\d+", pr.stdout + pr.stderr)
    if not url:
        raise Failed("PR not created: " + (pr.stderr.strip() or pr.stdout.strip())[:200])
    stat = git(repo_dir, "show", "--shortstat", "--format=", "HEAD").stdout.strip()
    return url.group(0), f"{branch_note} | {stat} | {tests}"


def merge_by_repo(path, lines, sep):
    """Write `lines` into the file, replacing earlier lines for the same repo; return the merged content."""
    merged = {}
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8").read().splitlines():
            if line.strip():
                merged[line.split(sep, 1)[0]] = line
    for line in lines:
        merged[line.split(sep, 1)[0]] = line
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(l + "\n" for l in merged.values()))
    return list(merged.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--wave", help="wave number (or range, e.g. 9-10) from dependency-tree.md")
    target.add_argument("--repos", nargs="+")
    ap.add_argument("--label", help="result file prefix (default: w<wave> or 'manual')")
    ap.add_argument("--dry-run", action="store_true",
                    help="make and verify the changes, write the PR body, but do not commit, push or open a PR")
    args = ap.parse_args()

    repos = [r for _, r in bump_module_deps.repos_for_waves(args.wave)] if args.wave else args.repos
    label = args.label or (f"w{args.wave}" if args.wave else "manual")
    bump_module_deps.set_nuget_wait(config.NUGET_WAIT_MINUTES)
    results, prs = [], []
    for repo in repos:
        try:
            url, detail = prepare(repo, args.dry_run)
            line = f"{repo}: PR {url} | {detail}" if url else f"{repo}: {detail}"
            if url:
                prs.append(f"{repo} {url}")
        except Failed as e:
            line = f"{repo}: FAILED ({e})"
        print(line, flush=True)
        results.append(line)
    # merge by repo, so re-running one fixed repo keeps the rest of the wave's lines and PRs
    results = merge_by_repo(config.work(f"{label}-prepare.txt"), results, ":")
    merge_by_repo(config.work(f"{label}-prs.txt"), prs, " ")
    failed = [r for r in results if ": FAILED" in r]
    print(f"\n{len(prs)} PR(s) opened, {len(failed)} FAILED. Results: {config.work(label + '-prepare.txt')}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
