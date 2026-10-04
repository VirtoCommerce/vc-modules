import requests
import json
from packaging import version
from html import escape

GITHUB_TOKEN = ""
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

session = requests.Session()
session.headers.update(HEADERS)

def list_releases(repo):
    url = f"https://api.github.com/repos/VirtoCommerce/{repo}/releases?per_page=100"
    resp = session.get(url, timeout=(5,10))
    resp.raise_for_status()
    return resp.json()

def filter_existing_tags(releases, old_ver, new_ver):
    start = version.parse(old_ver)
    end   = version.parse(new_ver)
    filtered = []
    for r in releases:
        tag = r.get("tag_name", "")
        try:
            ver = version.parse(tag)
        except:
            continue
        if start < ver <= end:
            filtered.append((ver, tag, r.get("body","")))
    filtered.sort(key=lambda x: x[0])
    return [(t, b) for _, t, b in filtered]

def build_html(modules):
    html = [
        "<!DOCTYPE html>",
        "<html lang='ru'><head><meta charset='utf-8'>",
        "<title>Release Notes</title>",
        "<style>",
        "  body {font-family: Arial, sans-serif; padding:20px;}",
        "  h1 {text-align:center;}",
        "  .module {margin-bottom:40px;}",
        "  .module h2 {color:#2c3e50;}",
        "  ul {margin:0; padding-left:20px;}",
        "  li {margin-bottom:15px;}",
        "  .tag {font-weight:bold; margin-top:10px;}",
        "</style>",
        "</head><body>",
        "<h1>Release Notes</h1>"
    ]

    for mod in modules:
        name    = escape(mod["name"])
        repo    = mod["url"].split("/")[0]
        old_ver = mod["oldVersion"]
        new_ver = mod["newVersion"]

        print(f"\nModule: {name}")
        print(f"Version range: {old_ver} → {new_ver}")

        releases = list_releases(repo)
        entries = filter_existing_tags(releases, old_ver, new_ver)
        tags = [tag for tag, _ in entries]
        print("Found tags:", tags or ["(no releases)"])

        html.append(f"<div class='module'><h2>{name}</h2>")
        html.append(f"<p>Range: <b>{old_ver}</b> → <b>{new_ver}</b></p>")

        if not entries:
            html.append("<p><i>There are no existing releases in this range.</i></p>")
        else:
            html.append("<ul>")
            for tag, body in entries:
                html.append(f"<li><div class='tag'>{tag}</div><div class='body'>{body or 'Release notes are missing'}</div></li>")
            html.append("</ul>")

        html.append("</div>")

    html.append("</body></html>")
    return "\n".join(html)

def main():
    with open("modules_config.json", encoding="utf-8") as f:
        modules = json.load(f)["modules"]

    html_content = build_html(modules)
    with open("release_notes.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print("\n✅ release_notes.html has been generated")

if __name__ == "__main__":
    main()
