"""
Shared release configuration loader for the src tooling.

Reads release.config.json (sibling of this file) and exposes the per-release
values + resolved paths so the tools are NOT hardcoded to one stable version.
To cut the next stable, edit release.config.json — not the scripts.

Path resolution is derived from THIS file's location (works regardless of the
machine's checkout path); only versions/strings come from the JSON.

Usage:
    import config
    bundle = json.load(open(config.CUR_BUNDLE, encoding="utf-8"))
    out_path = config.out("dependency-tree.md")
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_HERE, "release.config.json")

with open(_CONFIG_PATH, encoding="utf-8") as _f:
    _cfg = json.load(_f)

# --- raw config values ---
VERSION = int(_cfg["version"])
PREV_VERSION = int(_cfg["prevVersion"])
PLATFORM_VERSION = _cfg["platformVersion"]
THEME_VERSION = _cfg["themeVersion"]
THEME_URL = _cfg["themeUrlTemplate"].format(themeVersion=THEME_VERSION)
JIRA_TICKET = _cfg.get("jiraTicket", "")
BRANCH = _cfg.get("branch", f"feat/{JIRA_TICKET}-stable-{VERSION}")
OBSOLETE_REMOVAL_TICKET = _cfg.get("obsoleteRemovalTicket", "")
ORG = _cfg.get("githubOrg", "VirtoCommerce")
SOURCE_BRANCH = _cfg.get("sourceBranch", "dev")          # module PRs target it; the Release workflow runs on it
NUGET_WAIT_MINUTES = int(_cfg.get("nugetWaitMinutes", 30))
FLAKY_CHECKS = _cfg.get("flakyChecks", r"^(auto-tests / .*|swagger-validation)$")  # re-run once, never a blocker twice
PBC_REQUIRED_MODULES = _cfg.get("pbcRequiredModules", [])    # every pbc/*.json grouping must include these

# --- derived paths ---
# The vc-modules repo this tool lives in (src -> vc-modules). Bundles, the registry and the deliverables live here.
VC_MODULES = os.path.normpath(os.path.join(_HERE, ".."))
REGISTRY = os.path.join(VC_MODULES, "modules_v3.json")

# Source-repo root (vc-platform, vc-module-*): release.config.json `monorepoRoot`, defaulting to vc-modules'
# parent (the normal side-by-side checkout layout).
MONOREPO_ROOT = os.path.normpath(_cfg.get("monorepoRoot") or os.path.join(VC_MODULES, os.pardir))
ROOT = MONOREPO_ROOT  # alias: the repo-scanning tools glob ROOT/vc-platform and ROOT/vc-module-*
PLATFORM_DIR = os.path.join(MONOREPO_ROOT, "vc-platform")


def bundle_dir(v):
    """Path to bundles/v{v}."""
    return os.path.join(VC_MODULES, "bundles", f"v{v}")


CUR_BUNDLE = os.path.join(bundle_dir(VERSION), "package.json")
PREV_BUNDLE = os.path.join(bundle_dir(PREV_VERSION), "package.json")


def out(filename):
    """Path to a deliverable in the current bundle dir (bundles/v{VERSION}/<filename>)."""
    return os.path.join(bundle_dir(VERSION), filename)


# Per-cycle working files (wave results, PR lists, PR bodies, per-repo notes). Git-ignored, never a deliverable.
WORK_DIR = os.path.join(VC_MODULES, ".release-work", f"v{VERSION}")


def work(filename):
    """Path to a working file in .release-work/v{VERSION}/ (directory created on demand)."""
    path = os.path.join(WORK_DIR, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path
