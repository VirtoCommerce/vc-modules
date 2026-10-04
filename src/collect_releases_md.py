"""
Generate bundles/v{version}/release_notes.md (prev -> current) in the established Markdown style.
Versions/bundles come from release.config.json (see config.py).

For each module in the current bundle: old version comes from the previous bundle's package.json,
new version from the current bundle, repo name from the local module.manifest <id> -> repo folder
map. Fetches the GitHub release bodies for every published tag in the range (old, new] and emits
them under per-version headings.

Auth: reads a token from `gh auth token` (env GITHUB_TOKEN overrides) for API rate limits.
Usage: python collect_releases_md.py
"""
import glob
import json
import os
import re
import subprocess
import sys

import requests
from packaging import version

import config

ROOT = config.ROOT
PREV_BUNDLE = config.PREV_BUNDLE   # old versions (bundles/v{prevVersion})
CUR_BUNDLE = config.CUR_BUNDLE     # new versions (bundles/v{version})
OUT = config.out("release_notes.md")


def gh_token():
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True, shell=True).strip()
    except Exception:
        return ""


session = requests.Session()
token = gh_token()
if token:
    session.headers.update({"Authorization": f"Bearer {token}"})
session.headers.update({"Accept": "application/vnd.github.v3+json"})


def modules_of(pkg_path):
    d = json.load(open(pkg_path, encoding="utf-8"))
    gh = [s for s in d["Sources"] if s["Name"] == "GithubReleases"][0]
    return {m["Id"]: m["Version"] for m in gh["Modules"]}


def build_id_repo_map():
    """Map module id -> repo folder, using ONLY the canonical manifest at
    vc-module-X/src/<Project>.Web/module.manifest (exactly 4 path segments from ROOT).
    This excludes artifacts/ copies and stray flattened-path folders that pollute the tree."""
    idmap = {}
    for mf in glob.glob(os.path.join(ROOT, "vc-module-*", "**", "module.manifest"), recursive=True):
        rel = os.path.relpath(mf, ROOT).replace("\\", "/").split("/")
        # [repo, "src", "<Project>.Web", "module.manifest"]
        if len(rel) != 4 or rel[1] != "src" or not rel[2].endswith(".Web"):
            continue
        try:
            txt = open(mf, encoding="utf-8-sig").read()
        except Exception:
            continue
        m = re.search(r"<id>([^<]+)</id>", txt)
        if not m:
            continue
        idmap.setdefault(m.group(1).strip(), rel[0])
    return idmap


def list_releases(repo):
    url = f"https://api.github.com/repos/VirtoCommerce/{repo}/releases?per_page=100"
    out = []
    page = 1
    while True:
        resp = session.get(url + f"&page={page}", timeout=(5, 15))
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def in_range(releases, old_ver, new_ver):
    start = version.parse(old_ver) if old_ver else None
    end = version.parse(new_ver)
    rows = []
    for r in releases:
        tag = r.get("tag_name", "")
        try:
            ver = version.parse(tag)
        except Exception:
            continue
        if (start is None or start < ver) and ver <= end:
            rows.append((ver, tag, (r.get("body") or "").strip()))
    rows.sort(key=lambda x: x[0])
    return [(t, b) for _, t, b in rows]


def html_to_md(body):
    """Convert the simple HTML release bodies (<h3>/<ul>/<li> only) that newer GitHub
    releases use into the Markdown style of bundles/v14/release_notes.md."""
    if not body or "<" not in body:
        return body
    s = body
    s = re.sub(r"<h3>\s*(.*?)\s*</h3>", r"\n\n### \1\n", s, flags=re.S)
    s = s.replace("<ul>", "\n").replace("</ul>", "\n")
    s = re.sub(r"<li>\s*(.*?)\s*</li>", lambda m: "  * " + m.group(1).strip() + "\n", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)            # strip any stray tags
    s = re.sub(r"[ \t]+\n", "\n", s)         # trailing whitespace
    s = re.sub(r"\n{3,}", "\n\n", s)         # collapse blank runs
    return s.strip()


def anchor(name):
    return "#" + re.sub(r"[^a-z0-9]", "", name.lower())


def main():
    old = modules_of(PREV_BUNDLE)
    new = modules_of(CUR_BUNDLE)
    idrepo = build_id_repo_map()

    ids = sorted(new.keys(), key=str.lower)

    toc = ["- [{0}]({1})".format(i, anchor(i)) for i in ids]
    body = []

    for mid in ids:
        repo = idrepo.get(mid)
        old_v = old.get(mid)
        new_v = new[mid]
        sys.stderr.write(f"{mid}: {old_v or 'NEW'} -> {new_v} ({repo})\n")

        body.append(f"## {mid}\n")
        rng = f"`{old_v}` → `{new_v}`" if old_v else f"_(new in v{config.VERSION})_ → `{new_v}`"
        body.append(f"- **Versions:** {rng}")
        if repo:
            body.append(f"- **Repository:** [{repo}](https://github.com/VirtoCommerce/{repo})")
        body.append("")

        entries = []
        if repo:
            try:
                entries = in_range(list_releases(repo), old_v, new_v)
            except Exception as ex:
                sys.stderr.write(f"  ! {mid}: {ex}\n")

        if not entries:
            body.append("_No published releases in this range._\n")
        else:
            for tag, b in entries:
                b = html_to_md(b)
                body.append(f"### {tag}\n")
                body.append((b if b else "_Release notes are missing._") + "\n")
        body.append("---\n")

    md = []
    md.append("# Release Notes\n")
    md.append("Summary of changes by platform modules. Versions shown as previous → current.\n")
    md.append("## Table of contents\n")
    md.extend(toc)
    md.append("\n---\n")
    md.extend(body)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(md).rstrip() + "\n")

    sys.stderr.write(f"\nWrote {OUT} ({len(ids)} modules)\n")


if __name__ == "__main__":
    main()
