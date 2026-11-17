#!/usr/bin/env python3
"""Add the newest release .deb of every package in packages.yml to pool/, then prune.

Usage: sync_releases.py --pool <pool dir> [--keep N] [--owners <json out>]

The pool is the only state: a .deb whose canonical name (<Package>_<Version>_<Arch>.deb,
read from its control fields) is already there is skipped. Keeps the newest N versions of
each package (default 3, compared with `dpkg --compare-versions`) and deletes older ones.
Deletes every pool .deb whose Package is not shipped by any entry in packages.yml (a
package dropped from the list), but only when every entry resolved to a release: an entry
with no .deb release has an unknown Package name, so nothing is treated as orphaned then.
Writes `staged=<n>` and `removed=<n>` (pruned + orphaned files) to $GITHUB_OUTPUT (when
set), and with --owners a JSON map {Package: "owner/repo"} for the landing page. Fails if two entries ship the same
Package name, or if a release's Version is lower than one already published.
Needs `gh` authenticated (GH_TOKEN) with read access to every listed repo, and dpkg-deb.
"""
import argparse
import functools
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def gh_json(*args):
    return json.loads(subprocess.check_output(["gh", *args], text=True))


def control(deb, *fields):
    out = subprocess.check_output(["dpkg-deb", "-f", str(deb), *fields], text=True)
    values = dict(line.split(": ", 1) for line in out.strip().splitlines())
    return [values[f] for f in fields]


def vercmp(a, b):
    if a == b:
        return 0
    return -1 if subprocess.call(["dpkg", "--compare-versions", a, "lt", b]) == 0 else 1


def pick_release(entry):
    prefix = entry.get("tag_prefix", "")
    for rel in gh_json("api", f"repos/{entry['repo']}/releases?per_page=30"):
        if rel["draft"] or (rel["prerelease"] and not entry.get("prereleases")):
            continue
        if not rel["tag_name"].startswith(prefix):
            continue
        debs = [a for a in rel["assets"] if a["name"].endswith(".deb")]
        if debs:
            return rel["tag_name"], debs[0]["name"]
    return None, None


def pool_versions(pool):
    """{package: [(version, path), ...]} for every .deb in the pool."""
    found = {}
    for deb in pool.rglob("*.deb"):
        name, version = control(deb, "Package", "Version")
        found.setdefault(name, []).append((version, deb))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--keep", type=int, default=3)
    ap.add_argument("--owners")
    args = ap.parse_args()

    pool = Path(args.pool)
    pool.mkdir(parents=True, exist_ok=True)
    entries = yaml.safe_load((ROOT / "packages.yml").read_text())["packages"]
    published = pool_versions(pool)

    staged = 0
    removed = 0
    unresolved = []
    owners = {}
    with tempfile.TemporaryDirectory() as tmp:
        for entry in entries:
            tag, asset = pick_release(entry)
            if not tag:
                print(f"{entry['repo']}: no release with a .deb", file=sys.stderr)
                unresolved.append(entry["repo"])
                continue
            subprocess.check_call(["gh", "release", "download", tag, "-R", entry["repo"],
                                   "-p", asset, "-D", tmp, "--clobber"])
            deb = Path(tmp) / asset
            name, version, arch = control(deb, "Package", "Version", "Architecture")
            if name in owners:
                sys.exit(f"Package {name} is shipped by both {owners[name]} and {entry['repo']}")
            owners[name] = entry["repo"]
            versions = [v for v, _ in published.get(name, [])]
            if version in versions:
                print(f"{entry['repo']}: {name} {version} already published")
                deb.unlink()
                continue
            newest = max(versions, key=functools.cmp_to_key(vercmp), default=None)
            if newest and vercmp(version, newest) < 0:
                sys.exit(f"{entry['repo']}: {tag} ships {name} {version}, lower than published {newest}")
            target = pool / "main" / name[0] / name / f"{name}_{version.split(':')[-1]}_{arch}.deb"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(deb, target)
            published.setdefault(name, []).append((version, target))
            print(f"{entry['repo']}: staged {tag} as {target.relative_to(pool)}")
            staged += 1

    for name in sorted(set(published) - set(owners)):
        if unresolved:
            print(f"kept {name}: not in packages.yml, but orphan pruning is off because "
                  f"{', '.join(unresolved)} did not resolve", file=sys.stderr)
            continue
        for version, path in published.pop(name):
            print(f"removed {name} {version}: no entry in packages.yml ships it")
            path.unlink()
            removed += 1

    for name, versions in published.items():
        versions.sort(key=functools.cmp_to_key(lambda a, b: vercmp(a[0], b[0])), reverse=True)
        for version, path in versions[args.keep:]:
            print(f"pruned {name} {version}")
            path.unlink()
            removed += 1

    if args.owners:
        Path(args.owners).write_text(json.dumps(owners, indent=2, sort_keys=True) + "\n")

    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a") as fh:
            fh.write(f"staged={staged}\nremoved={removed}\n")


if __name__ == "__main__":
    main()
