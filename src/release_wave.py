"""
CI gate + release for one prepared wave (the PR list written by prepare_wave.py).

  1. CI gate, all PRs in parallel: watch each PR's checks. A PR whose ONLY failures match `flakyChecks`
     (release.config.json; the auto-tests legs and swagger-validation) gets its failed jobs re-run ONCE. Any other
     failure, or a flake that fails again, STOPS the wave: nothing in it is merged.
  2. Release, only when every PR is green, per repo:
       - guard: skip (and STOP) a PR that is already merged or a repo whose Release workflow is already queued/running,
         so Release is never triggered twice (e.g. by an orphaned watcher of an interrupted run);
       - squash-merge with --admin (needs the bypass permission), delete the branch;
       - trigger the `Release` workflow on `sourceBranch`, watch it, then wait for the new GitHub release and its
         module .zip.
NuGet publishing lags the GitHub release; the next wave's prepare_wave.py waits for it.

Run ONE wave per invocation (background jobs are time-limited). Result: .release-work/v{N}/<label>-release.txt,
first line GREEN-RELEASED or STOPPED.

Usage: python release_wave.py --label w9
       python release_wave.py --label w9 --gate-only       # CI gate only, nothing merged
"""
import argparse
import json
import re
import subprocess
import threading
import time

import config

FLAKY = re.compile(config.FLAKY_CHECKS)
LOCK = threading.Lock()


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def gh_json(*args):
    out = gh(*args)
    return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else None


def repo_of(name):
    return f"{config.ORG}/{name}"


def failing_checks(repo, pr):
    out = gh("pr", "checks", pr, "-R", repo_of(repo))
    return [line.split("\t")[0] for line in out.stdout.splitlines() if "\tfail\t" in line]


def watch_checks(repo, pr):
    gh("pr", "checks", pr, "-R", repo_of(repo), "--watch", "--interval", "60")


def gate(repo, pr, log):
    time.sleep(45)   # let the checks register
    watch_checks(repo, pr)
    fails = failing_checks(repo, pr)
    if fails:
        if any(not FLAKY.match(f) for f in fails):
            log(f"{repo} #{pr}: RED (not a known flake) -> {'; '.join(fails)}")
            return
        runs = gh_json("run", "list", "-R", repo_of(repo), "--branch", config.BRANCH, "--workflow", "Module CI",
                       "--limit", "1", "--json", "databaseId") or []
        if not runs:
            log(f"{repo} #{pr}: RED (no CI run to re-run) -> {'; '.join(fails)}")
            return
        log(f"{repo} #{pr}: known flake ({'; '.join(fails)}) -> re-running run {runs[0]['databaseId']} once")
        gh("run", "rerun", str(runs[0]["databaseId"]), "-R", repo_of(repo), "--failed")
        time.sleep(45)
        watch_checks(repo, pr)
        fails = failing_checks(repo, pr)
        if fails:
            log(f"{repo} #{pr}: RED after re-run -> {'; '.join(fails)}")
            return
    log(f"{repo} #{pr}: GREEN")


def latest_release(repo):
    data = gh_json("release", "view", "-R", repo_of(repo), "--json", "tagName,assets")
    return (data["tagName"], [a["name"] for a in data["assets"] if a["name"].endswith(".zip")]) if data else (None, [])


def merge_and_trigger(repo, pr, log):
    """Return the release tag before the merge, or None when this repo must not be released now."""
    state = (gh_json("pr", "view", pr, "-R", repo_of(repo), "--json", "state,mergeable") or {})
    if state.get("state") == "MERGED":
        log(f"{repo} #{pr}: STOP - already merged by another process; not triggering Release")
        return None
    runs = gh_json("run", "list", "-R", repo_of(repo), "--workflow", "release.yml", "--branch", config.SOURCE_BRANCH,
                   "--limit", "5", "--json", "status") or []
    if any(r["status"] != "completed" for r in runs):
        log(f"{repo} #{pr}: STOP - a Release run is already queued/running")
        return None
    if state.get("mergeable") != "MERGEABLE":
        log(f"{repo} #{pr}: STOP - not mergeable ({state.get('mergeable')})")
        return None
    before, _ = latest_release(repo)
    gh("pr", "merge", pr, "-R", repo_of(repo), "--squash", "--admin", "--delete-branch")
    if (gh_json("pr", "view", pr, "-R", repo_of(repo), "--json", "state") or {}).get("state") != "MERGED":
        log(f"{repo} #{pr}: STOP - merge failed")
        return None
    if gh("workflow", "run", "Release", "-R", repo_of(repo), "--ref", config.SOURCE_BRANCH).returncode:
        log(f"{repo}: STOP - release trigger failed")
        return None
    return before or ""


def await_release(repo, before, log):
    time.sleep(20)
    runs = gh_json("run", "list", "-R", repo_of(repo), "--workflow", "release.yml", "--limit", "1",
                   "--json", "databaseId") or []
    if not runs:
        log(f"{repo}: STOP - no Release run found")
        return
    run_id = str(runs[0]["databaseId"])
    if gh("run", "watch", run_id, "-R", repo_of(repo), "--exit-status").returncode:
        log(f"{repo}: STOP - release workflow failed (run {run_id})")
        return
    for _ in range(60):
        tag, zips = latest_release(repo)
        if tag and tag != before:
            log(f"{repo}: RELEASED {tag} (was {before}) zip: {','.join(zips) or 'MISSING'}")
            return
        time.sleep(60)
    log(f"{repo}: STOP - no GitHub release after 60 min (still {before})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True, help="the prepare_wave.py label, e.g. w9")
    ap.add_argument("--gate-only", action="store_true", help="run the CI gate only; never merge or release")
    args = ap.parse_args()
    prs = [line.split() for line in open(config.work(f"{args.label}-prs.txt"), encoding="utf-8") if line.strip()]
    prs = [(repo, url.rsplit("/", 1)[1]) for repo, url in prs]
    lines = []

    def log(message):
        with LOCK:
            lines.append(message)
            print(message, flush=True)

    def parallel(fn, items):
        threads = [threading.Thread(target=fn, args=item) for item in items]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    parallel(lambda repo, pr: gate(repo, pr, log), prs)
    if any("RED" in l for l in lines):
        verdict = "STOPPED - not released (CI)"
    elif args.gate_only:
        verdict = "GREEN (gate only, nothing merged)"
    else:
        to_release = []
        for repo, pr in prs:
            before = merge_and_trigger(repo, pr, log)
            if before is not None:
                to_release.append((repo, before))
        parallel(lambda repo, before: await_release(repo, before, log), to_release)
        verdict = "STOPPED - release problem" if any(re.search(r"STOP|MISSING", l) for l in lines) else "GREEN-RELEASED"
    result = config.work(f"{args.label}-release.txt")
    open(result, "w", encoding="utf-8").write(verdict + "\n" + "\n".join(sorted(lines)) + "\n")
    print(f"\n{verdict}. Result: {result}")
    raise SystemExit(0 if verdict.startswith("GREEN") else 1)


if __name__ == "__main__":
    main()
