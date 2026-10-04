"""
Run `npm audit fix` (never --force) on a module's admin-UI Web project(s) and verify the build still works.

Per `src/*/package-lock.json`: audit counts before -> `npm audit fix` -> counts after -> `npm run webpack:build`.
If the build fails after the fix, the lockfile is restored from git, so the module never ships a broken admin UI.
Only the lockfile is expected to change (transitive dev-tooling bumps).

Usage: python npm_audit_fix.py <repo_dir>          (prints one JSON object per Web project)
"""
import argparse
import glob
import json
import os
import subprocess

SHELL = os.name == "nt"   # npm is npm.cmd on Windows


def _audit_counts(web_dir):
    out = subprocess.run(["npm", "audit", "--json"], cwd=web_dir, capture_output=True, text=True,
                         encoding="utf-8", shell=SHELL).stdout
    try:
        v = json.loads(out)["metadata"]["vulnerabilities"]
    except (ValueError, KeyError):
        return "n/a"
    return " ".join(f"{k}={v[k]}" for k in ("critical", "high", "moderate", "low") if v.get(k)) or "none"


def _changed_packages(repo_dir, lock_rel):
    """'name old → new' for every lockfile package whose version changed against HEAD."""
    head = subprocess.run(["git", "show", f"HEAD:{lock_rel.replace(os.sep, '/')}"], cwd=repo_dir,
                          capture_output=True, text=True, encoding="utf-8")
    if head.returncode != 0:
        return []
    old = json.loads(head.stdout).get("packages", {})
    new = json.load(open(os.path.join(repo_dir, lock_rel), encoding="utf-8")).get("packages", {})
    return sorted({f"{k.split('node_modules/')[-1]} {old[k].get('version', '')} → {new[k].get('version', '')}"
                   for k in new if k in old and old[k].get("version") != new[k].get("version")})


def fix(repo_dir):
    results = []
    for lock in sorted(glob.glob(os.path.join(repo_dir, "src", "*", "package-lock.json"))):
        web = os.path.dirname(lock)
        lock_rel = os.path.relpath(lock, repo_dir)
        before = _audit_counts(web)
        fixed = subprocess.run(["npm", "audit", "fix", "--no-fund", "--no-progress"], cwd=web,
                               capture_output=True, text=True, encoding="utf-8", shell=SHELL)
        after = _audit_counts(web)
        build = subprocess.run(["npm", "run", "webpack:build"], cwd=web, capture_output=True, text=True,
                               encoding="utf-8", shell=SHELL)
        result = {"project": os.path.basename(web), "before": before, "after": after,
                  "auditFixExitCode": fixed.returncode, "webpack": "OK" if build.returncode == 0 else "FAILED"}
        if build.returncode != 0:
            subprocess.run(["git", "checkout", "--", lock_rel], cwd=repo_dir)
            result["reverted"] = True
            result["changed"] = []
        else:
            result["changed"] = _changed_packages(repo_dir, lock_rel)
        results.append(result)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_dir")
    for result in fix(ap.parse_args().repo_dir):
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
