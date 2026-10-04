"""
Stable-release Step 0 audit: obsolete-code inventory + risk.

Read-only. Scans vc-platform and every module repo referenced by a bundle's
package.json for [Obsolete(...)] members, classifies which qualify for removal
under the Stable-release policy (no DiagnosticId OR DiagnosticId < VC0012), and
emits a Markdown audit report.

Usage:
    python audit_obsolete.py [--bundle ..\\v15\\package.json] [--out ..\\v15\\obsolete_removal_audit.md]
"""
import argparse
import glob
import json
import os
import re

import config

ROOT = config.ROOT  # <monorepo root>, e.g. C:/Projects/git/VirtoCommerce
VC = ROOT

OBSOLETE_RE = re.compile(r"\[\s*Obsolete\b", re.IGNORECASE)
DIAG_RE = re.compile(r"DiagnosticId\s*=\s*\"([^\"]+)\"")
VC_NUM_RE = re.compile(r"VC0*(\d+)", re.IGNORECASE)
MSG_RE = re.compile(r"Obsolete\s*\(\s*\"((?:[^\"\\]|\\.)*)\"")
VIS_RE = re.compile(r"\b(public|protected internal|protected|internal|private protected|private)\b")
KIND_RE = re.compile(r"\b(class|interface|enum|struct|record)\b")


def compute_downstream(wanted, registry_path):
    """transitive downstream dependent count per module id, from modules_v3.json stable deps."""
    try:
        from packaging import version as _v
        data = json.load(open(registry_path, encoding="utf-8"))
    except Exception:
        return {}
    byid = {m["Id"]: m for m in data}
    deps = {}
    for mid in wanted:
        m = byid.get(mid)
        if not m:
            deps[mid] = []
            continue
        stables = [v for v in m["Versions"] if not v.get("VersionTag")]
        if not stables:
            deps[mid] = []
            continue
        best = max(stables, key=lambda v: _v.parse(v["Version"]))
        deps[mid] = [d["Id"] for d in (best.get("Dependencies") or []) if d["Id"] in wanted]
    # reverse adjacency
    revadj = {mid: set() for mid in wanted}
    for mid in wanted:
        for d in deps.get(mid, []):
            revadj.setdefault(d, set()).add(mid)
    # transitive closure of dependents
    out = {}
    for mid in wanted:
        seen = set()
        stack = list(revadj.get(mid, set()))
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(revadj.get(n, set()))
        out[mid] = len(seen)
    return out


def build_id_map(wanted):
    """module id -> repo folder name, from module.manifest files."""
    idmap = {}
    for mf in glob.glob(os.path.join(VC, "vc-module-*", "**", "module.manifest"), recursive=True):
        try:
            txt = open(mf, encoding="utf-8-sig").read()
        except Exception:
            continue
        m = re.search(r"<id>([^<]+)</id>", txt)
        if not m:
            continue
        mid = m.group(1).strip()
        norm = mf.replace("\\", "/")
        seg = norm.split("/vc-module-")
        if len(seg) < 2:
            continue
        repo = "vc-module-" + seg[1].split("/")[0]
        idmap.setdefault(mid, repo)
    return {k: v for k, v in idmap.items() if k in wanted}


def collect_attribute(lines, i):
    """Given index i where '[Obsolete' starts, return (full_attr_text, next_index_after_attr)."""
    text = ""
    depth = 0
    j = i
    started = False
    while j < len(lines):
        for ch in lines[j]:
            text += ch
            if ch == "[":
                depth += 1
                started = True
            elif ch == "]":
                depth -= 1
        text += "\n"
        j += 1
        if started and depth <= 0:
            break
    return text, j


def find_member(lines, j):
    """From index j (first line after attribute), find the member declaration line."""
    while j < len(lines):
        s = lines[j].strip()
        if not s or s.startswith("//") or s.startswith("/*") or s.startswith("*") or s.startswith("#"):
            j += 1
            continue
        if s.startswith("["):  # another attribute
            _, j = collect_attribute(lines, j)
            continue
        return lines[j].strip(), j
    return "", j


def classify_kind(sig):
    if KIND_RE.search(sig):
        return KIND_RE.search(sig).group(1)
    if "(" in sig:
        return "method"
    if "{" in sig or "=>" in sig or sig.rstrip().endswith(";"):
        return "property/field"
    return "member"


def classify_vis(sig):
    m = VIS_RE.search(sig)
    return m.group(1) if m else "(default)"


def qualifies(diag):
    """Removal set: no DiagnosticId, or VC0001..VC0011 (< VC0012)."""
    if not diag:
        return True, None
    m = VC_NUM_RE.search(diag)
    if not m:
        return False, None  # non-VC diagnostic id, keep
    n = int(m.group(1))
    return (n < 12), n


def risk(vis, kind):
    # (default) visibility on an [Obsolete] member here is virtually always an
    # interface or enum member -> implicitly public -> cross-module API.
    if vis in ("public", "protected", "protected internal", "(default)"):
        return "High"
    if vis in ("internal", "private protected"):
        return "Medium"
    return "Low"


def scan_repo(repo_path):
    rows = []
    src = os.path.join(repo_path, "src")
    base = src if os.path.isdir(src) else repo_path
    for cs in glob.glob(os.path.join(base, "**", "*.cs"), recursive=True):
        n = cs.replace("\\", "/")
        if "/obj/" in n or "/bin/" in n or "/Migrations/" in n:
            continue
        try:
            lines = open(cs, encoding="utf-8-sig").read().splitlines()
        except Exception:
            continue
        i = 0
        while i < len(lines):
            m = OBSOLETE_RE.search(lines[i])
            # Real attribute only: the line (stripped) must START with '[' — excludes matches
            # inside // line comments, * block-comment bodies, and string literals/code.
            if m and lines[i].lstrip().startswith("["):
                attr, j = collect_attribute(lines, i)
                diag_m = DIAG_RE.search(attr)
                diag = diag_m.group(1) if diag_m else ""
                msg_m = MSG_RE.search(attr)
                msg = (msg_m.group(1) if msg_m else "").strip()
                q, num = qualifies(diag)
                sig, k = find_member(lines, j)
                vis = classify_vis(sig)
                kind = classify_kind(sig)
                rows.append({
                    "file": os.path.relpath(cs, repo_path).replace("\\", "/"),
                    "line": i + 1,
                    "sig": sig[:160],
                    "diag": diag or "none",
                    "num": num,
                    "msg": msg[:200],
                    "vis": vis,
                    "kind": kind,
                    "qualifies": q,
                    "risk": risk(vis, kind) if q else "",
                })
                i = max(k, i + 1)
            else:
                i += 1
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=config.CUR_BUNDLE)
    ap.add_argument("--out", default=config.out("obsolete_removal_audit.md"))
    args = ap.parse_args()

    bundle = json.load(open(args.bundle, encoding="utf-8"))
    gh = [s for s in bundle["Sources"] if s["Name"] == "GithubReleases"][0]
    wanted = {m["Id"] for m in gh["Modules"]}
    idmap = build_id_map(wanted)
    missing = wanted - set(idmap)
    registry = config.REGISTRY
    downstream = compute_downstream(wanted, registry)
    downstream["VirtoCommerce.Platform"] = len(wanted)  # platform underlies everything

    targets = [("VirtoCommerce.Platform", os.path.join(VC, "vc-platform"))]
    for mid in sorted(idmap):
        targets.append((mid, os.path.join(VC, idmap[mid])))

    all_rows = {}
    for mid, path in targets:
        all_rows[mid] = scan_repo(path)

    # build report
    out = []
    out.append(f"# Stable {config.VERSION} — Obsolete-code removal audit (Step 0)\n")
    out.append("> Read-only inventory. **No code has been changed.** Generated by `src/audit_obsolete.py`.\n")
    out.append("Removal policy: remove `[Obsolete]` members with **no DiagnosticId** OR "
               "**DiagnosticId VC0001–VC0011** (strictly `< VC0012`). VC0012+ are kept.\n")
    out.append("Risk heuristic: `High` = public/protected, or interface/enum members "
               "(implicitly public — cross-repo break potential); `Medium` = internal; "
               "`Low` = private. Visibility shown as `(default)` means an interface/enum member.\n")

    # global summary
    tot_q = sum(1 for mid in all_rows for r in all_rows[mid] if r["qualifies"])
    tot_all = sum(len(all_rows[mid]) for mid in all_rows)
    high = sum(1 for mid in all_rows for r in all_rows[mid] if r["qualifies"] and r["risk"] == "High")
    med = sum(1 for mid in all_rows for r in all_rows[mid] if r["qualifies"] and r["risk"] == "Medium")
    low = sum(1 for mid in all_rows for r in all_rows[mid] if r["qualifies"] and r["risk"] == "Low")
    out.append("## Summary\n")
    out.append(f"- Repos scanned: **{len(targets)}** (platform + {len(targets)-1} modules)")
    if missing:
        out.append(f"- ⚠️ Unmapped module ids (not scanned): {sorted(missing)}")
    out.append(f"- Total `[Obsolete]` members found: **{tot_all}**")
    out.append(f"- **Qualify for removal: {tot_q}**  (kept VC0012+: {tot_all - tot_q})")
    out.append(f"- Visibility of qualifying removals — public/interface/enum (High): **{high}**, "
               f"internal (Med): **{med}**, private (Low): **{low}**")
    out.append("- Effectively **all qualifying removals are public API**, so the real risk driver is "
               "**blast radius** (downstream dependents) — see the per-repo table below.\n")

    # per-repo counts table — sorted by blast radius (downstream dependents) then qualify count
    out.append("### Per-repo counts (qualifying), sorted by blast radius\n")
    out.append("**Blast radius** = number of other bundle modules that transitively depend on this "
               "repo. Removing public API here can break that many downstream repos — they must be "
               "recompiled (in wave order, against `local-nuget`) to confirm.\n")
    out.append("| Repo | Blast radius | Total Obsolete | Qualify | DiagnosticIds (qualifying) |")
    out.append("|---|--:|--:|--:|---|")
    rep_rows = []
    for mid, _ in targets:
        rows = all_rows[mid]
        q = [r for r in rows if r["qualifies"]]
        if not rows:
            continue
        diags = {}
        for r in q:
            diags[r["diag"]] = diags.get(r["diag"], 0) + 1
        dstr = ", ".join(f"{k}:{v}" for k, v in sorted(diags.items()))
        rep_rows.append((downstream.get(mid, 0), len(q), mid, len(rows), dstr))
    for ds, nq, mid, ntot, dstr in sorted(rep_rows, key=lambda x: (-x[0], -x[1])):
        out.append(f"| {mid} | {ds} | {ntot} | {nq} | {dstr} |")
    out.append("")

    # detailed rows per repo — ordered by blast radius (highest-risk repos first)
    out.append("## Detailed inventory (qualifying members only)\n")
    ordered_targets = sorted(targets, key=lambda t: -downstream.get(t[0], 0))
    for mid, _ in ordered_targets:
        q = [r for r in all_rows[mid] if r["qualifies"]]
        if not q:
            continue
        out.append(f"### {mid}  ({len(q)} to remove)\n")
        out.append("| Risk | File:Line | Vis | Kind | DiagId | Member | Replacement (from message) |")
        out.append("|---|---|---|---|---|---|---|")
        for r in sorted(q, key=lambda x: ({"High": 0, "Medium": 1, "Low": 2}.get(x["risk"], 3), x["file"])):
            sig = r["sig"].replace("|", "\\|")
            msg = r["msg"].replace("|", "\\|")
            out.append(f"| {r['risk']} | {r['file']}:{r['line']} | {r['vis']} | {r['kind']} | "
                       f"{r['diag']} | `{sig}` | {msg} |")
        out.append("")

    open(args.out, "w", encoding="utf-8").write("\n".join(out))
    print(f"Wrote {args.out}")
    print(f"Repos: {len(targets)}  Total obsolete: {tot_all}  Qualify: {tot_q}  (High {high} / Med {med} / Low {low})")
    if missing:
        print("UNMAPPED:", sorted(missing))


if __name__ == "__main__":
    main()
