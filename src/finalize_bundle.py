"""
Finalize bundles/v{version}/package.json from the actually-released module versions.

Read-only except writing package.json. For each module in the bundle, finds its repo
(via module.manifest <id>) and its released version, and updates the bundle. Sets
PlatformVersion/PlatformImageTag and the theme from release.config.json.

Version source (--source):
  github (default)  the repo's latest non-prerelease GitHub release (gh CLI); the release must carry a .zip asset.
                    Use this for a CI-driven cycle, where releases are cut from `dev` by the Release workflow and
                    local clones may sit on other branches or already carry the next VersionPrefix.
  local             Directory.Build.props <VersionPrefix> of the local clone (the local-first workflow).

Usage: python finalize_bundle.py [--source github|local]
"""
import argparse
import glob
import json
import os
import re
import subprocess

import config

ROOT = config.ROOT
BUNDLE = config.CUR_BUNDLE
PLATFORM_VERSION = config.PLATFORM_VERSION
THEME_VERSION = config.THEME_VERSION
THEME_URL = config.THEME_URL


def build_id_map():
    idmap = {}
    for mf in glob.glob(os.path.join(ROOT, "vc-module-*", "**", "module.manifest"), recursive=True):
        try:
            txt = open(mf, encoding="utf-8-sig").read()
        except Exception:
            continue
        m = re.search(r"<id>([^<]+)</id>", txt)
        if not m:
            continue
        repo = "vc-module-" + mf.replace("\\", "/").split("/vc-module-")[1].split("/")[0]
        idmap.setdefault(m.group(1).strip(), os.path.join(ROOT, repo))
    return idmap


def released_version(repo_path):
    dbp = os.path.join(repo_path, "Directory.Build.props")
    if not os.path.isfile(dbp):
        return None
    m = re.search(r"<VersionPrefix>([^<]+)</VersionPrefix>", open(dbp, encoding="utf-8-sig").read())
    return m.group(1).strip() if m else None


def released_version_github(repo_path):
    """Latest non-prerelease GitHub release tag of the repo, or None (also None when it has no .zip asset)."""
    repo = os.path.basename(os.path.normpath(repo_path))
    out = subprocess.run(["gh", "release", "view", "-R", f"VirtoCommerce/{repo}", "--json", "tagName,isPrerelease,assets"],
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        return None
    rel = json.loads(out.stdout)
    if rel.get("isPrerelease") or not any(a["name"].endswith(".zip") for a in rel.get("assets", [])):
        return None
    return rel["tagName"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["github", "local"], default="github")
    source = ap.parse_args().source
    resolve = released_version_github if source == "github" else released_version

    bundle = json.load(open(BUNDLE, encoding="utf-8"))
    bundle["PlatformVersion"] = PLATFORM_VERSION
    bundle["PlatformImageTag"] = PLATFORM_VERSION
    bundle["ThemeB2BVue"] = THEME_URL

    idmap = build_id_map()
    gh = [s for s in bundle["Sources"] if s["Name"] == "GithubReleases"][0]
    changed, missing = [], []
    for mod in gh["Modules"]:
        repo = idmap.get(mod["Id"])
        ver = resolve(repo) if repo else None
        if ver and ver != mod["Version"]:
            changed.append(f"{mod['Id']}: {mod['Version']} -> {ver}")
            mod["Version"] = ver
        elif not ver:
            missing.append(mod["Id"])

    json.dump(bundle, open(BUNDLE, "w", encoding="utf-8"), indent=2)
    open(BUNDLE, "a", encoding="utf-8").write("\n")
    print(f"Platform={PLATFORM_VERSION} Theme={THEME_VERSION}; source={source}; updated {len(changed)} modules")
    for c in changed:
        print("  " + c)
    if missing:
        print("UNRESOLVED (left as-is):", missing)


if __name__ == "__main__":
    main()
