"""
Bump a module repo to the release's platform version.

  * `VirtoCommerce.Platform.*` PackageReference      -> platformVersion (release.config.json)
  * `module.manifest` <platformVersion>               -> platformVersion
  * `FluentAssertions` PackageReference              -> the platform's supported range

`VirtoCommerce.Platform.Hangfire` is never bumped: it is retired (frozen at 3.1051.0, no newer package). Modules move
to the Platform.Core job API instead; `prepare_wave.py` refuses to prepare a repo that still references Hangfire.

Byte-level edits: line endings and formatting are preserved. Idempotent.

Usage: python bump_platform.py <repo_dir> [--version 3.1076.0]
"""
import argparse
import glob
import os
import re

import config

PLATFORM_REF = re.compile(rb'(Include="VirtoCommerce\.Platform\.(?!Hangfire")[A-Za-z.]+"\s+Version=")[^"]+(")')
MANIFEST_PLATFORM = re.compile(rb'(<platformVersion>)[^<]+(</platformVersion>)')
FLUENT_ASSERTIONS = re.compile(rb'(Include="FluentAssertions"\s+Version=")[^"]+(")')
FLUENT_ASSERTIONS_RANGE = b'[7.2.2, 8.0.0)'
SKIP = re.compile(r'[\\/](bin|obj|node_modules)[\\/]')


def _edit(path, patterns):
    data = open(path, 'rb').read()
    new = data
    for rx, rep in patterns:
        new = rx.sub(rep, new)
    if new != data:
        open(path, 'wb').write(new)
        return True
    return False


def bump(repo_dir, platform_version=config.PLATFORM_VERSION):
    """Apply the bump; return the relative paths of the files that changed."""
    ver = platform_version.encode()
    changed = []
    for path in glob.glob(os.path.join(repo_dir, '**', '*.csproj'), recursive=True):
        if SKIP.search(path):
            continue
        if _edit(path, [(PLATFORM_REF, lambda m: m.group(1) + ver + m.group(2)),
                        (FLUENT_ASSERTIONS, lambda m: m.group(1) + FLUENT_ASSERTIONS_RANGE + m.group(2))]):
            changed.append(os.path.relpath(path, repo_dir))
    for path in glob.glob(os.path.join(repo_dir, 'src', '*', 'module.manifest')):
        if _edit(path, [(MANIFEST_PLATFORM, lambda m: m.group(1) + ver + m.group(2))]):
            changed.append(os.path.relpath(path, repo_dir))
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('repo_dir')
    ap.add_argument('--version', default=config.PLATFORM_VERSION)
    args = ap.parse_args()
    for path in bump(args.repo_dir, args.version):
        print(f'  bumped: {path}')


if __name__ == '__main__':
    main()
