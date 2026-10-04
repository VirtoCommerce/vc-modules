"""
Collect the raw material for bundles/v{N}/breaking_changes.md from the cycle's merged PRs.

Searches the org for merged PRs whose title carries the cycle's Jira key (`jiraTicket`) or the obsolete-removal key
(`obsoleteRemovalTicket`), and extracts each PR's `## Breaking changes` section. Sections that say only "None." (or the
standard "module.manifest floors raised" line) are dropped. The output is a working file to write breaking_changes.md
from, by hand: grouped by key, then repo, with PR links.

Writing the document from the PRs, not from memory, is the point: every signature or behavior change was already
described by the PR that made it.

Usage: python collect_breaking_changes.py        -> .release-work/v{N}/breaking_changes_raw.md
"""
import json
import re
import subprocess

import config

SECTION = re.compile(r"## Breaking changes\s*\n(.*?)(?=\n## |\Z)", re.S)
TRIVIAL = re.compile(r"(None\.?|None in code\..*floors are raised.*)", re.S)


def merged_prs(key):
    out = subprocess.run(["gh", "search", "prs", f"{key} in:title", "--owner", config.ORG, "--merged",
                          "--limit", "200", "--json", "repository,number,title,url"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


def body(repo, number):
    return subprocess.run(["gh", "pr", "view", str(number), "-R", f"{config.ORG}/{repo}", "--json", "body",
                           "-q", ".body"], capture_output=True, text=True, encoding="utf-8").stdout


def main():
    lines = [f"# Stable {config.VERSION}: breaking-change sections from merged PRs\n"]
    for key in filter(None, (config.JIRA_TICKET, config.OBSOLETE_REMOVAL_TICKET)):
        prs = sorted(merged_prs(key), key=lambda p: (p["repository"]["name"], p["number"]))
        kept = 0
        lines.append(f"\n## {key} ({len(prs)} merged PRs)\n")
        for pr in prs:
            repo = pr["repository"]["name"]
            m = SECTION.search(body(repo, pr["number"]) or "")
            text = m.group(1).strip() if m else "(no Breaking changes section)"
            if TRIVIAL.fullmatch(text):
                continue
            kept += 1
            lines.append(f"### {repo} [#{pr['number']}]({pr['url']}) {pr['title']}\n\n{text}\n")
        print(f"{key}: {len(prs)} merged PRs, {kept} with breaking changes")
    path = config.work("breaking_changes_raw.md")
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
