"""
Bump a module's VirtoCommerce module dependencies to their latest releases.

Every stable-release wave builds on the modules the earlier waves just released, so each module repo must reference
the **latest released version** of the modules it depends on, in both places:
  * `*.csproj`  <PackageReference Include="VirtoCommerce.<X>.Core|Data|..." Version="..."/>
  * `module.manifest`  <dependency id="VirtoCommerce.<X>" version="..."/>
VirtoCommerce.Platform.* is not touched here: that is the platform bump (one version for all, release.config.json).
Packages the platform ships besides Platform.* (VirtoCommerce.Testing) are moved to `platformVersion` too.

"Latest released" = the module repo's latest (non-prerelease) GitHub release. Before applying, the tool checks that
the version is already on nuget.org, because CI restores from there and publishing can lag the GitHub release by minutes. Between waves, pass `--wait-nuget MINUTES` so the tool polls
nuget.org until every target version is listed instead of skipping it.

Usage:
  python bump_module_deps.py --check  <repo> [<repo> ...] [--ref origin/dev]   # report stale refs, change nothing
  python bump_module_deps.py --apply  <repo> [<repo> ...] [--wait-nuget 30]     # rewrite the working tree
  python bump_module_deps.py --check  --waves 2-8 [--ref origin/dev]            # every repo of those waves
<repo> is a directory name under the monorepo root (e.g. vc-module-catalog). Waves come from
bundles/v{N}/dependency-tree.md. Only upward bumps are made; anything not resolvable to a bundle module is reported, not
changed. Line endings are preserved byte-for-byte.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from functools import lru_cache

from packaging import version

import config

ROOT = config.MONOREPO_ROOT
ORG = "VirtoCommerce"
PKG_REF = re.compile(rb'(<PackageReference\s+Include=")(VirtoCommerce\.[A-Za-z0-9.]+)("\s+Version=")([^"]+)(")')
MANIFEST_DEP = re.compile(rb'(<dependency\s+id=")(VirtoCommerce\.[A-Za-z0-9.]+)("\s+version=")([^"]+)(")')
MANIFEST_ID = re.compile(r"<id>([^<]+)</id>")
# Packages built and versioned with the platform (vc-platform repo) that are not named VirtoCommerce.Platform.*.
PLATFORM_VERSIONED = {"VirtoCommerce.Testing"}


def _git(repo, *args):
    return subprocess.run(["git", "-C", os.path.join(ROOT, repo), *args], capture_output=True, check=True).stdout


@lru_cache(maxsize=None)
def module_index():
    """module id -> repo dir, and nuget package id -> module id, from the repos on disk."""
    module_to_repo, package_to_module = {}, {}
    for manifest in glob.glob(os.path.join(ROOT, "vc-module-*", "src", "*", "module.manifest")):
        repo = os.path.relpath(manifest, ROOT).split(os.sep)[0]
        match = MANIFEST_ID.search(open(manifest, encoding="utf-8-sig").read())
        if not match:
            continue
        module_id = match.group(1).strip()
        module_to_repo.setdefault(module_id, repo)
        for csproj in glob.glob(os.path.join(ROOT, repo, "src", "**", "*.csproj"), recursive=True):
            if re.search(r"[\\/](bin|obj|node_modules)[\\/]", csproj):
                continue
            package_to_module.setdefault(os.path.splitext(os.path.basename(csproj))[0], module_id)
    return module_to_repo, package_to_module


@lru_cache(maxsize=None)
def latest_release(repo):
    """Latest non-prerelease GitHub release tag of a repo (e.g. '3.1047.0')."""
    out = subprocess.run(["gh", "release", "view", "-R", f"{ORG}/{repo}", "--json", "tagName,isPrerelease"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    data = json.loads(out.stdout)
    return None if data.get("isPrerelease") else data["tagName"].lstrip("v")


_nuget_wait_minutes = 0


def on_nuget(package_id, ver):
    """True when nuget.org lists the version. With --wait-nuget, polls once a minute up to that many minutes."""
    url = f"https://api.nuget.org/v3-flatcontainer/{package_id.lower()}/index.json"
    for attempt in range(_nuget_wait_minutes + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                if ver in json.load(response).get("versions", []):
                    return True
        except Exception:
            pass
        if attempt < _nuget_wait_minutes:
            print(f"    waiting for {package_id} {ver} on nuget.org ({attempt + 1}/{_nuget_wait_minutes} min)", flush=True)
            time.sleep(60)
    return False


def latest_for_module(module_id):
    repo = module_index()[0].get(module_id)
    return latest_release(repo) if repo else None


def repo_files(repo, ref):
    """(path, bytes) for every csproj and module.manifest, from `ref` (git) or the working tree (ref=None)."""
    if ref:
        names = _git(repo, "ls-tree", "-r", "--name-only", ref).decode().splitlines()
        names = [n for n in names if n.endswith(".csproj") or n.endswith("module.manifest")]
        return [(n, _git(repo, "show", f"{ref}:{n}")) for n in names]
    base = os.path.join(ROOT, repo)
    paths = glob.glob(os.path.join(base, "**", "*.csproj"), recursive=True) + \
        glob.glob(os.path.join(base, "src", "*", "module.manifest"))
    paths = [p for p in paths if not re.search(r"[\\/](bin|obj|node_modules)[\\/]", p)]
    return [(os.path.relpath(p, base), open(p, "rb").read()) for p in paths]


def plan(repo, ref=None):
    """Return (changes, notes): changes = [(file, kind, id, old, new)], notes = unresolved/lagging items."""
    _, package_to_module = module_index()
    own_module = next((m for m, r in module_index()[0].items() if r == repo), None)
    changes, notes = [], []
    for path, data in repo_files(repo, ref):
        is_manifest = path.endswith("module.manifest")
        pattern = MANIFEST_DEP if is_manifest else PKG_REF
        for match in pattern.finditer(data):
            dep_id, current = match.group(2).decode(), match.group(4).decode()
            if dep_id.startswith("VirtoCommerce.Platform."):
                continue  # platform bump, handled separately
            if not is_manifest and dep_id in PLATFORM_VERSIONED:
                if current != config.PLATFORM_VERSION:
                    changes.append((path, "package", dep_id, current, config.PLATFORM_VERSION))
                continue
            module_id = dep_id if is_manifest else package_to_module.get(dep_id)
            if not module_id or module_id == own_module:
                if not is_manifest:
                    notes.append(f"{path}: {dep_id} {current} - not a bundle module package, left as is")
                continue
            latest = latest_for_module(module_id)
            if not latest:
                notes.append(f"{path}: {dep_id} - no release found for {module_id}")
                continue
            try:
                stale = version.parse(current.strip("[]() ")) < version.parse(latest)
            except version.InvalidVersion:
                notes.append(f"{path}: {dep_id} has a non-plain version '{current}', left as is")
                continue
            if stale:
                if not is_manifest and not on_nuget(dep_id, latest):
                    notes.append(f"{path}: {dep_id} {latest} is not on nuget.org yet - retry later")
                    continue
                changes.append((path, "manifest" if is_manifest else "package", dep_id, current, latest))
    return changes, notes


def apply(repo, changes):
    base = os.path.join(ROOT, repo)
    by_file = {}
    for path, kind, dep_id, old, new in changes:
        by_file.setdefault(path, []).append((kind, dep_id, old, new))
    for path, items in by_file.items():
        full = os.path.join(base, path)
        data = open(full, "rb").read()
        for kind, dep_id, old, new in items:
            pattern = MANIFEST_DEP if kind == "manifest" else PKG_REF
            data = pattern.sub(lambda m, d=dep_id, o=old, n=new: (
                m.group(1) + m.group(2) + m.group(3) + n.encode() + m.group(5)
                if m.group(2).decode() == d and m.group(4).decode() == o else m.group(0)), data)
        open(full, "wb").write(data)


def repos_for_waves(spec):
    lo, _, hi = spec.partition("-")
    lo, hi = int(lo), int(hi or lo)
    tree = open(config.out("dependency-tree.md"), encoding="utf-8").read()
    module_to_repo = module_index()[0]
    repos = []
    for wave in range(lo, hi + 1):
        section = re.search(rf"## Wave {wave}\b.*?(?=\n## |\Z)", tree, re.S)
        if not section:
            continue
        for module_id in re.findall(r"^\| (VirtoCommerce\.[A-Za-z0-9.]+) \|", section.group(0), re.M):
            repo = module_to_repo.get(module_id)
            if repo:
                repos.append((wave, repo))
            else:
                print(f"! wave {wave}: no local repo for {module_id}", file=sys.stderr)
    return repos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    ap.add_argument("repos", nargs="*")
    ap.add_argument("--waves", help="e.g. 2-8 (reads dependency-tree.md)")
    ap.add_argument("--ref", help="git ref to read in --check mode (e.g. origin/dev); default: working tree")
    ap.add_argument("--wait-nuget", type=int, default=0, metavar="MINUTES",
                    help="poll nuget.org up to MINUTES for a release that is not listed yet (use between waves)")
    args = ap.parse_args()
    global _nuget_wait_minutes
    _nuget_wait_minutes = args.wait_nuget
    if args.apply and args.ref:
        ap.error("--ref is only for --check")

    targets = [(None, r) for r in args.repos] + (repos_for_waves(args.waves) if args.waves else [])
    stale_repos = 0
    for wave, repo in targets:
        changes, notes = plan(repo, args.ref)
        label = f"[wave {wave}] " if wave else ""
        status = f"{len(changes)} stale ref(s)" if changes else "up to date"
        print(f"### {label}{repo}: {status}")
        for path, kind, dep_id, old, new in changes:
            print(f"    {kind:8} {dep_id}: {old} -> {new}   ({path})")
        for note in notes:
            print(f"    note: {note}")
        if changes:
            stale_repos += 1
            if args.apply:
                apply(repo, changes)
                print(f"    APPLIED {len(changes)} change(s)")
    print(f"\n{stale_repos} of {len(targets)} repo(s) have stale VirtoCommerce module references.")


if __name__ == "__main__":
    main()
