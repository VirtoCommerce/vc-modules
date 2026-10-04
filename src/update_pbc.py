"""
Update the PBC (Packaged Business Capability) groupings, pbc/*.json, to the current stable bundle.

Per grouping:
  * PlatformVersion -> the bundle's;
  * a bundle module -> its bundle version;
  * a module outside the bundle -> its newest STABLE registry version whose PlatformVersion <= the bundle's
    (reported, because it was not rebuilt for this platform);
  * every module in `pbcRequiredModules` (release.config.json; Stable 16: VirtoCommerce.BackgroundJobs, the job engine)
    is added when missing;
  * the set is closed: every missing required dependency is added (bundle version, else newest compatible), repeatedly,
    so each grouping stays installable on its own, as the previous stable's groupings were.
Each file keeps its indentation and module order; new modules go in at their alphabetical position.
Ends with a dependency check (every non-optional dependency present at >= its floor).

Usage: python update_pbc.py [--apply] [--registry-ref origin/master]      (dry run without --apply)
"""
import argparse
import glob
import json
import os

from packaging.version import Version

import config
import validate_bundle


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--registry-ref", default="origin/master")
    args = ap.parse_args()

    reg = validate_bundle.registry(args.registry_ref)
    bundle = json.load(open(config.CUR_BUNDLE, encoding="utf-8"))
    platform = bundle["PlatformVersion"]
    bundled = validate_bundle.bundle_modules(bundle)

    def stable(module_id):
        return [v for v in reg.get(module_id, {}).get("Versions", []) if not v.get("VersionTag")]

    def entry(module_id, ver):
        return next((v for v in stable(module_id) if v["Version"] == ver), None)

    def newest_compatible(module_id):
        found = [v for v in stable(module_id) if Version(v["PlatformVersion"]) <= Version(platform)]
        return max(found, key=lambda v: Version(v["Version"])) if found else None

    def target_version(module_id):
        return bundled.get(module_id) or (newest_compatible(module_id) or {}).get("Version")

    def insert_sorted(mods, item):
        for i, m in enumerate(mods):
            if m["Id"].lower() > item["Id"].lower():
                mods.insert(i, item)
                return
        mods.append(item)

    problems = 0
    for path in sorted(glob.glob(os.path.join(config.VC_MODULES, "pbc", "*.json"))):
        raw = open(path, "rb").read()
        text = raw.decode("utf-8-sig").replace("\r\n", "\n")
        doc = json.loads(text)
        mods = doc["Modules"] if "Modules" in doc else \
            next(s["Modules"] for s in doc["Sources"] if s["Name"] == "GithubReleases")
        notes = []
        print(f"\n## {os.path.basename(path)}: platform {doc['PlatformVersion']} -> {platform}")
        doc["PlatformVersion"] = platform

        for m in mods:
            if m["Id"] in bundled:
                m["Version"] = bundled[m["Id"]]
                continue
            newest = newest_compatible(m["Id"])
            if not newest:
                notes.append(f"  ! {m['Id']} {m['Version']}: no stable version for platform <= {platform}; left as is")
                continue
            notes.append(f"  ~ {m['Id']} {m['Version']} -> {newest['Version']} "
                         f"(not in the bundle; built for platform {newest['PlatformVersion']})")
            m["Version"] = newest["Version"]

        for required in config.PBC_REQUIRED_MODULES:
            if not any(m["Id"] == required for m in mods) and target_version(required):
                insert_sorted(mods, {"Id": required, "Version": target_version(required)})
                notes.append(f"  + {required} {target_version(required)} added (pbcRequiredModules)")

        added = True
        while added:   # close the set over required dependencies
            added = False
            have = {m["Id"] for m in mods}
            for m in list(mods):
                for dep in (entry(m["Id"], m["Version"]) or {}).get("Dependencies") or []:
                    ver = target_version(dep["Id"])
                    if dep["Optional"] or dep["Id"] in have or not ver:
                        continue
                    insert_sorted(mods, {"Id": dep["Id"], "Version": ver})
                    have.add(dep["Id"])
                    notes.append(f"  + {dep['Id']} {ver} added (required by {m['Id']})")
                    added = True
        print("\n".join(notes) or "  (versions only)")

        have = {m["Id"]: m["Version"] for m in mods}
        for m in mods:
            e = entry(m["Id"], m["Version"])
            if not e:
                print(f"  ? {m['Id']} {m['Version']}: no stable registry entry")
                problems += 1
                continue
            for dep in e.get("Dependencies") or []:
                got = have.get(dep["Id"])
                if (got is None and not dep["Optional"]) or (got and Version(got) < Version(dep["Version"])):
                    print(f"  DEPENDENCY: {m['Id']} {m['Version']} needs {dep['Id']} >= {dep['Version']}, has {got}")
                    problems += 1

        if args.apply:
            second = text.split("\n")[1]
            indent = len(second) - len(second.lstrip(" "))
            out = json.dumps(doc, indent=indent, ensure_ascii=False) + ("\n" if text.endswith("\n") else "")
            if b"\r\n" in raw:
                out = out.replace("\n", "\r\n")
            open(path, "wb").write(out.encode("utf-8"))
    print(f"\n{'APPLIED' if args.apply else 'dry run'}; {problems} problem(s)")
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
