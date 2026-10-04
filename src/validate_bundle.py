"""
Validate bundles/v{N}/package.json against the published module registry (modules_v3.json on origin/master).

For every module in the bundle:
  * a STABLE registry entry exists for the pinned version (no VersionTag);
  * its PlatformVersion equals the bundle's PlatformVersion, and its PackageUrl is the GitHub-release .zip;
  * every non-optional dependency is in the bundle at or above its floor.
Also checks that the platform release is not a prerelease and that the theme URL resolves.

A missing stable entry usually means the module's master-CI "Publish Manifest" step lost a push race on
vc-modules/master (Stable 16: Catalog 3.1048.0 conflicted with its own dev alpha publish): the release is fine, the
registry entry has to be added.

Usage: python validate_bundle.py [--registry-ref origin/master] [--bundle path/to/package.json]
"""
import argparse
import json
import subprocess
import sys
import urllib.request

from packaging.version import Version

import config


def registry(ref):
    subprocess.run(["git", "-C", config.VC_MODULES, "fetch", "-q", "origin"], check=False)
    data = subprocess.run(["git", "-C", config.VC_MODULES, "show", f"{ref}:modules_v3.json"], capture_output=True,
                          check=True).stdout
    return {m["Id"]: m for m in json.loads(data.decode("utf-8-sig"))}


def bundle_modules(bundle):
    return {m["Id"]: m["Version"] for s in bundle["Sources"] if s["Name"] == "GithubReleases" for m in s["Modules"]}


def validate(bundle, reg):
    problems = []
    platform = Version(bundle["PlatformVersion"])
    modules = bundle_modules(bundle)
    for module_id, ver in sorted(modules.items()):
        entry = next((v for v in reg.get(module_id, {}).get("Versions", [])
                      if v["Version"] == ver and not v.get("VersionTag")), None)
        if not entry:
            problems.append(f"{module_id} {ver}: no stable entry in modules_v3.json")
            continue
        if Version(entry["PlatformVersion"]) != platform:
            problems.append(f"{module_id} {ver}: built for platform {entry['PlatformVersion']}, bundle is {platform}")
        if "github.com" not in (entry.get("PackageUrl") or ""):
            problems.append(f"{module_id} {ver}: PackageUrl is not a GitHub release ({entry.get('PackageUrl')})")
        for dep in entry.get("Dependencies") or []:
            have = modules.get(dep["Id"])
            if have is None and not dep["Optional"]:
                problems.append(f"{module_id} {ver}: required dependency {dep['Id']} is not in the bundle")
            elif have and Version(have) < Version(dep["Version"]):
                problems.append(f"{module_id} {ver}: needs {dep['Id']} >= {dep['Version']}, bundle has {have}")
    release = subprocess.run(["gh", "release", "view", bundle["PlatformVersion"], "-R", f"{config.ORG}/vc-platform",
                              "--json", "isPrerelease"], capture_output=True, text=True)
    if release.returncode != 0 or json.loads(release.stdout).get("isPrerelease"):
        problems.append(f"platform {bundle['PlatformVersion']}: no stable GitHub release")
    try:
        urllib.request.urlopen(urllib.request.Request(bundle["ThemeB2BVue"], method="HEAD"), timeout=30)
    except Exception as e:  # noqa: BLE001 - report any failure to reach the theme
        problems.append(f"theme {bundle['ThemeB2BVue']}: {e}")
    return modules, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry-ref", default="origin/master")
    ap.add_argument("--bundle", default=config.CUR_BUNDLE)
    args = ap.parse_args()
    bundle = json.load(open(args.bundle, encoding="utf-8"))
    modules, problems = validate(bundle, registry(args.registry_ref))
    print(f"{len(modules)} modules, platform {bundle['PlatformVersion']}")
    print("\n".join(problems) or "no problems")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
